"""Utilities for SQS."""
import json
import logging
import os
import signal
import sys
import tempfile
import time
from datetime import datetime
from typing import Any

import boto3

from core.utils.model_utils import get_json_schema, get_system_prompt, get_user_prompt
from core.utils.video_utils import sample_video_frames

from .model_client import ModelClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Configuration from environment variables
OUTPUT_BUCKET = os.getenv("OUTPUT_BUCKET", "ai-chaperone-dev")
DYNAMO_TABLE = os.getenv("DYNAMO_TABLE", "ai-chaperone-video-moderation-jobs")
QUEUE_NAME = os.getenv("SQS_QUEUE_NAME", "ai-chaperone-image-processing-queue")
REGION = os.getenv("AWS_REGION", "us-east-2")


class SQSPollingServer:
    """Server that polls AWS SQS."""

    def __init__(self, queue_name: str, region: str="us-east-2") -> None:
        """Initialize the SQS polling server."""
        self.queue_name = queue_name
        self.region = region
        self.running = True

        # Initialize AWS clients
        self.sqs = boto3.client("sqs", region_name=region)
        self.s3 = boto3.client("s3", region_name=region)
        self.dynamo_table = boto3.client("dynamodb", region_name=region).Table(
            DYNAMO_TABLE,
        )
        self.model_client = ModelClient()


        # Get queue URL
        try:
            response = self.sqs.get_queue_url(QueueName=queue_name)
            self.queue_url = response["QueueUrl"]
            logger.info("Connected to queue: %s", self.queue_url)
        except Exception:
            logger.exception("Failed to get queue URL")
            raise

    def _parse_s3_url(self, s3_url: str) -> tuple[Any, Any] | tuple[None, None]:
        """Parse S3 URL to get bucket and key."""
        # s3://bucket-name/path/to/object
        if s3_url.startswith("s3://"):
            s3_url = s3_url[5:]
            parts = s3_url.split("/", 1)
            if len(parts) == 2:
                return parts[0], parts[1]
        return None, None

    def _parse_llm_response(self, response: dict) -> dict[str, Any] | None:  # noqa: PLR0911
        """Parse the LLM response.

        Check for validity and get JSON
        """
        if not isinstance(response, dict):
            logger.error("Invalid LLM response: expected dict, got %s", type(response).__name__)
            logger.error("Invalid LLM response: expected dict, got %s", type(response).__name__)
            return None

        choices = response.get("choices")
        if not isinstance(choices, list) or not choices:
            logger.error("Invalid LLM response: 'choices' missing or empty")
            return None

        choice = choices[0]
        if not isinstance(choice, dict):
            logger.error("Invalid LLM response: first choice is not a dict")
            return None

        message = choice.get("message")
        if not isinstance(message, dict):
            logger.error("Invalid LLM response: 'message' missing or not a dict")
            return None

        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            logger.error("Invalid LLM response: 'content' missing or empty")
            return None

        logger.info("Raw LLM content: %s", content)
        logger.info("Stripped LLM content: %s", content[8:-3].strip())
        try:
            # if content begins and ends with triple backticks, remove them
            if content.startswith("```json") and content.endswith("```"):
                content = content[8:-3].strip()
            parsed_content = json.loads(content)
        except json.JSONDecodeError:
            logger.exception("Failed to parse LLM response content as JSON")
            return None
        else:
            return parsed_content

    def analyze_video_for_issues(
        self, video_path: str,
        fps: int = 1,
        max_frames: int = 50,
    ) -> list[Any] | None:
        """Analyze a video for any issues by sampling frames and sending them to the model.

        Args:
            video_path (str): Path to the video file to analyze
            fps (int): frames per second for sampling
            max_frames (int): number of frames to sample

        Returns:
            str: Model response about any issues found in the video frames

        """
        logger.info("Analyzing video for issues: %s", video_path)

        client = ModelClient()

        try:
            # Sample frames from the video
            logger.info("Sampling frames from video: %s", video_path)

            # check if the file is there
            if not os.path.exists(video_path):
                logger.error("Video file does not exist: %s", video_path)
                return None

            sampled_images = sample_video_frames(
                video_path, fps=fps, max_frames=max_frames,
            )

            if not sampled_images:
                logger.error("No frames were sampled from the video")
                return None

            logger.info("Successfully sampled %s frames", len(sampled_images))

            # Prepare messages with the sampled images using VLLM server syntax
            messages = [
                {
                    "role": "system",
                    "content": get_system_prompt(),
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": get_user_prompt(),
                        },
                    ] + [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{image}"},
                        } for image in sampled_images
                    ],
                },
            ]

            # Send to model for analysis
            logger.info("Sending frames to model for analysis")
            response = client.chat_completion(
                messages, temperature=0.3, extra_body={"guided_json": get_json_schema()},
            )

            if not response:
                logger.error("No response received from model")
                return None

        except Exception:
            logger.exception("Error analyzing video")
            return None
        else:
            logger.info("Analysis completed successfully")
            return response

    def process_message(self, message_body: str) -> bool:
        """Parent function that orchestrates processing of a single message."""
        parsed = self._parse_message(message_body)
        if not parsed:
            return False

        job_id = parsed["job_id"]
        video_s3_url = parsed["video_s3_url"]

        logger.info("Processing job: %s", job_id)
        logger.info("Video URL: %s", video_s3_url)

        video_path = self._download_video(s3_url=video_s3_url, job_id=job_id)
        if video_path is None:
            return False

        try:
            logger.info("Calling analyze_video_for_issues with path: %s", video_path)
            response = self.analyze_video_for_issues(video_path=video_path)
            if response is None:
                return False

            llm_result = self._parse_llm_response(response)
            if llm_result is None:
                logger.error("Failed to parse LLM response")
                return False

            logger.info("LLM Result: %s", json.dumps(llm_result, indent=2))
            logger.info("Successfully processed job: %s", job_id)

            s3_url = self._save_result_to_s3(job_id, llm_result)
            if s3_url is None:
                return False

            return self._update_dynamo(job_id, s3_url)

        finally:
            try:
                if video_path and os.path.exists(video_path):
                    os.remove(video_path)
                    logger.info("Deleted temporary video: %s", video_path)
            except Exception as e:
                logger.warning(f"Failed to delete temporary video {video_path}: {e}")

    def _parse_message(self, message_body: str) -> dict[str, Any] | None:
        """Parse and validate incoming message JSON."""
        try:
            data = json.loads(message_body)
        except json.JSONDecodeError:
            logger.exception("Failed to parse message JSON")
            return None

        job_id = data.get("job_id")
        video_s3_url = data.get("video_s3_url")

        if not job_id or not video_s3_url:
            logger.error("Missing required fields: job_id or video_s3_url")
            return None

        return {"job_id": job_id, "video_s3_url": video_s3_url}

    def _download_video(self, s3_url: str, job_id: str | None = None) -> str | None:
        """Download video content from S3."""
        bucket, key = self._parse_s3_url(s3_url)
        if not bucket or not key:
            logger.error("Invalid S3 URL format: %s", s3_url)
            return None

        try:
            response = self.s3.get_object(Bucket=bucket, Key=key)
            # Save the video to a temporary file
            # Create a temporary directory for video files
            temp_dir = os.path.join(tempfile.gettempdir(), "video_processing")
            os.makedirs(temp_dir, exist_ok=True)

            # Use job_id for filename with original extension
            file_extension = os.path.splitext(key)[-1] or ".mp4"
            video_path = os.path.join(temp_dir, f"{job_id}{file_extension}")
            with open(video_path, "wb") as f:
                f.write(response["Body"].read())

        except Exception:
            logger.exception("Failed to download video from %s", f"s3://{bucket}/{key}")
            return None

        else:
            return video_path

    def _log_video_preview(self, video_path: str) -> None:
        """Log a short preview of the video for debugging."""
        logger.info("Video preview: %s", video_path)

    def _build_messages(self, request_type: str="safety")-> list[dict[Any, Any]] | None:
        """Build messages for the LLM call."""
        try:
            user_prompt = get_user_prompt(output_type=request_type)
            return [
                {"role": "system", "content": get_system_prompt()},
                {"role": "user", "content": user_prompt},
            ]
        except Exception:
            logger.exception("Failed to build prompts")
            return None

    def _call_llm(self, messages: list[dict[Any, Any]]) -> list[Any] | None:
        """Call the LLM and return raw response."""
        try:
            return self.model_client.chat_completion(messages, temperature=0.3)
        except Exception:
            logger.exception("LLM call failed")
            return None

    def _save_result_to_s3(self, job_id: str, llm_result: dict[str, Any] | str, output_type: str="safety") -> str | None:
        """Persist LLM result JSON to S3 and return the s3:// URL."""
        result_key = f"moderation-results/{job_id}/image_llm_{output_type}_result.json"
        try:
            self.s3.put_object(
                Bucket=OUTPUT_BUCKET,
                Key=result_key,
                Body=json.dumps(llm_result).encode("utf-8"),
                ContentType="application/json",
            )
            url = f"s3://{OUTPUT_BUCKET}/{result_key}"
            logger.info("Image LLM result saved to %s", url)
        except Exception:
            logger.exception("Failed to save Image LLM result to S3")
            return None
        else:
            return url

    def _update_dynamo(self, job_id: str, result_s3_url: str) -> bool:
        """Update DynamoDB with job status and result location."""
        url_var = "video_llm_result_s3_url"
        is_complete = True
        try:
            self.dynamo_table.update_item(
                Key={"job_id": job_id},
                UpdateExpression=f"SET {url_var} = :url, video_complete = :complete, updated_at = :time",
                ExpressionAttributeValues={
                    ":url": result_s3_url,
                    ":complete": is_complete,
                    ":time": datetime.utcnow().isoformat(),
                },
            )
            logger.info("DynamoDB updated for job_id: %s", job_id)
        except Exception:
            logger.exception("Failed to update Dynamo DB for job_id %s", job_id)
            return False
        else:
            return True

    def poll_queue(self) -> None:
        """Poll the SQS queue for messages."""
        while self.running:
            try:
                # Long polling with 20 second wait time
                response = self.sqs.receive_message(
                    QueueUrl=self.queue_url,
                    MaxNumberOfMessages=1,  # Process up to 1 message at once
                    WaitTimeSeconds=20,  # Long polling
                    VisibilityTimeout=60,  # 1 minute to process
                )

                messages = response.get("Messages", [])

                if messages:
                    logger.info("Received %s message(s)", len(messages))

                    for message in messages:
                        # Process the message
                        success = self.process_message(message["Body"])

                        if success:
                            # Delete message from queue after successful processing
                            self.sqs.delete_message(
                                QueueUrl=self.queue_url,
                                ReceiptHandle=message["ReceiptHandle"]
                            )
                            logger.info("Message deleted from queue")
                        else:
                            # Message will become visible again after VisibilityTimeout
                            logger.warning("Message processing failed, will retry later")
                else:
                    logger.debug("No messages in queue")

            except KeyboardInterrupt:
                logger.info("Received interrupt signal")
                self.shutdown()
            except Exception:
                logger.exception("Error polling queue")
                time.sleep(5)  # Wait before retrying

    def shutdown(self) -> None:
        """Gracefully shutdown the server."""
        logger.info("Shutting down server...")
        self.running = False

    def run(self) -> None:
        """Start the polling server."""
        logger.info("Starting SQS polling server for queue: %s", self.queue_name)
        logger.info("Press Ctrl+C to stop")

        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, lambda s, f: self.shutdown())
        signal.signal(signal.SIGTERM, lambda s, f: self.shutdown())

        # Start polling
        self.poll_queue()

        logger.info("Server stopped")


def main() -> None:
    """Run main entry point."""
    try:
        # Create and run the server
        server = SQSPollingServer(QUEUE_NAME, REGION)
        server.run()
    except Exception:
        logger.exception("Failed to start server")
        sys.exit(1)


if __name__ == "__main__":
    main()
