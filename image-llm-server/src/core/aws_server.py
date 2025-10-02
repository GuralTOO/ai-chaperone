import boto3
import json
import time
import logging
from datetime import datetime
import signal
import sys
from model_client import ModelClient
from core.utils.model_utils import get_system_prompt, get_user_prompt, get_json_schema
from core.utils.video_utils import sample_video_frames 
import tempfile
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

OUTPUT_BUCKET = os.getenv("OUTPUT_BUCKET", "ai-chaperone-dev")
DYNAMO_TABLE = os.getenv("DYNAMO_TABLE", "ai-chaperone-video-moderation-jobs")


class SQSPollingServer:
    def __init__(self, queue_name, region='us-east-2'):
        """Initialize the SQS polling server"""
        self.queue_name = queue_name
        self.region = region
        self.running = True
        
        # Initialize AWS clients
        self.sqs = boto3.client('sqs', region_name=region)
        self.s3 = boto3.client('s3', region_name=region)
        self.dynamo_table = boto3.resource('dynamodb', region_name=region).Table(DYNAMO_TABLE)
        self.model_client = ModelClient()


        # Get queue URL
        try:
            response = self.sqs.get_queue_url(QueueName=queue_name)
            self.queue_url = response['QueueUrl']
            logger.info(f"Connected to queue: {self.queue_url}")
        except Exception as e:
            logger.error(f"Failed to get queue URL: {e}")
            raise
    
    def _parse_s3_url(self, s3_url):
        """Parse S3 URL to get bucket and key"""
        # s3://bucket-name/path/to/object
        if s3_url.startswith('s3://'):
            s3_url = s3_url[5:]
            parts = s3_url.split('/', 1)
            if len(parts) == 2:
                return parts[0], parts[1]
        return None, None
    
    def _parse_llm_response(self, response):
        """Parse the LLM response:
        
            "reason": "detailed explanation of analysis and scoring rationale"
            "categories": ["list of violated categories, or empty array if none"],
            "category_scores": [list of scores corresponding to categories, or empty array if none],
            "critical": "DROP/LOW/MEDIUM/HIGH",
            "critical_score_confidence": "1-10 confidence rating"       
    
        """
        if not isinstance(response, dict):
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
        
        logger.info(f"Raw LLM content: {content}")
        logger.info(f"Stripped LLM content: {content[8:-3].strip()}")
        try:
            # if content begins and ends with triple backticks, remove them
            if content.startswith("```json") and content.endswith("```"):
                content = content[8:-3].strip()
            parsed_content = json.loads(content)
            return parsed_content
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response content as JSON: {e}")
            return None



    def analyze_video_for_issues(self, video_path: str, fps: int = 1, max_frames: int = 50):
        """
        Analyze a video for any issues by sampling frames and sending them to the model.
        
        Args:
            video_path (str): Path to the video file to analyze
        
        Returns:
            str: Model response about any issues found in the video frames
        """
        logger.info(f"Analyzing video for issues: {video_path}")

        client = ModelClient()
        
        try:
            # Sample frames from the video
            logger.info(f"Sampling frames from video: {video_path}")

            # check if the file is there
            if not os.path.exists(video_path):
                logger.error(f"Video file does not exist: {video_path}")
                return None

            sampled_images = sample_video_frames(video_path, fps=fps, max_frames=max_frames)
            
            if not sampled_images:
                logger.error("No frames were sampled from the video")
                return None
            
            logger.info(f"Successfully sampled {len(sampled_images)} frames")
            
            # Prepare messages with the sampled images using VLLM server syntax
            messages = [
                {
                    "role": "system",
                    "content": get_system_prompt()
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": get_user_prompt()
                        }
                    ] + [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{image}"}
                        } for image in sampled_images
                    ]
                }
            ]
            
            # Send to model for analysis
            logger.info("Sending frames to model for analysis")
            response = client.chat_completion(messages, temperature=0.3, extra_body={"guided_json": get_json_schema()})
            
            if response:
                logger.info("Analysis completed successfully")
                return response
            else:
                logger.error("No response received from model")
                return None
                
        except Exception as e:
            logger.error(f"Error analyzing video: {str(e)}")
            return None

    def process_message(self, message_body):
        """Parent function that orchestrates processing of a single message."""
        parsed = self._parse_message(message_body)
        if not parsed:
            return False

        job_id = parsed["job_id"]
        video_s3_url = parsed["video_s3_url"]

        logger.info(f"Processing job: {job_id}")
        logger.info(f"Video URL: {video_s3_url}")

        video_path = self._download_video(s3_url=video_s3_url, job_id=job_id)
        if video_path is None:
            return False

        try: 
            logger.info(f"Calling analyze_video_for_issues with path: {video_path}")
            response = self.analyze_video_for_issues(video_path=video_path)
            if response is None:
                return False
            
            llm_result = self._parse_llm_response(response)
            if llm_result is None:
                logger.error("Failed to parse LLM response")
                return False

            logger.info(f"LLM Result: {json.dumps(llm_result, indent=2)}")
            logger.info(f"Successfully processed job: {job_id}")

            s3_url = self._save_result_to_s3(job_id, llm_result)
            if s3_url is None:
                return False

            if not self._update_dynamo(job_id, s3_url):
                return False
            
            return True
        
        finally:
            try:
                if video_path and os.path.exists(video_path):
                    os.remove(video_path)
                    logger.info(f"Deleted temporary video: {video_path}")
            except Exception as e:
                logger.warning(f"Failed to delete temporary video {video_path}: {e}")


    def _parse_message(self, message_body):
        """Parse and validate incoming message JSON."""
        try:
            data = json.loads(message_body)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse message JSON: {e}")
            return None

        job_id = data.get('job_id')
        video_s3_url = data.get('video_s3_url')

        if not job_id or not video_s3_url:
            logger.error("Missing required fields: job_id or video_s3_url")
            return None

        return {"job_id": job_id, "video_s3_url": video_s3_url}

    def _download_video(self, s3_url, job_id=None):
        """Download video content from S3."""
        bucket, key = self._parse_s3_url(s3_url)
        if not bucket or not key:
            logger.error(f"Invalid S3 URL format: {s3_url}")
            return None

        try:
            response = self.s3.get_object(Bucket=bucket, Key=key)
            # Save the video to a temporary file
            # Create a temporary directory for video files
            temp_dir = os.path.join(tempfile.gettempdir(), "video_processing")
            os.makedirs(temp_dir, exist_ok=True)
            
            # Use job_id for filename with original extension
            file_extension = os.path.splitext(key)[-1] or '.mp4'
            video_path = os.path.join(temp_dir, f"{job_id}{file_extension}")
            with open(video_path, 'wb') as f:
                f.write(response['Body'].read())
            return video_path

        except Exception as e:
            logger.error(f"Failed to download video from s3://{bucket}/{key}: {e}")
            return None

    def _log_video_preview(self, video_path):
        """Log a short preview of the video for debugging."""
        logger.info(f"Video preview: {video_path}")

    def _build_messages(self, transcript_content, request_type="safety"):
        """Build messages for the LLM call."""
        try:
            user_prompt = get_user_prompt(transcript_content, type=request_type)
            return [
                {"role": "system", "content": get_system_prompt()},
                {"role": "user", "content": user_prompt},
            ]
        except Exception as e:
            logger.error(f"Failed to build prompts: {e}")
            return None

    def _call_llm(self, messages):
        """Call the LLM and return raw response."""
        try:
            return self.model_client.chat_completion(messages, temperature=0.3)
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return None

    def _save_result_to_s3(self, job_id, llm_result, type="safety"):
        """Persist LLM result JSON to S3 and return the s3:// URL."""
        result_key = f"moderation-results/{job_id}/image_llm_{type}_result.json"
        try:
            self.s3.put_object(
                Bucket=OUTPUT_BUCKET,
                Key=result_key,
                Body=json.dumps(llm_result).encode('utf-8'),
                ContentType='application/json'
            )
            url = f"s3://{OUTPUT_BUCKET}/{result_key}"
            logger.info(f"Image LLM result saved to {url}")
            return url
        except Exception as e:
            logger.error(f"Failed to save Image LLM result to S3: {e}")
            return None

    def _update_dynamo(self, job_id, result_s3_url):
        """Update DynamoDB with job status and result location."""
        url_var = "video_llm_result_s3_url"
        isComplete = True
        try:
            self.dynamo_table.update_item(
                Key={'job_id': job_id},
                UpdateExpression=f"SET {url_var} = :url, video_complete = :complete, updated_at = :time",
                ExpressionAttributeValues={
                    ':url': result_s3_url,
                    ':complete': isComplete,
                    ':time': datetime.utcnow().isoformat()
                }
            )
            logger.info(f"DynamoDB updated for job_id: {job_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to update Dynamo DB for job_id {job_id}: {e}")
            return False

    
    def poll_queue(self):
        """Poll the SQS queue for messages"""
        while self.running:
            try:
                # Long polling with 20 second wait time
                response = self.sqs.receive_message(
                    QueueUrl=self.queue_url,
                    MaxNumberOfMessages=1,  # Process up to 1 message at once
                    WaitTimeSeconds=20,  # Long polling
                    VisibilityTimeout=60  # 1 minute to process
                )
                
                messages = response.get('Messages', [])
                
                if messages:
                    logger.info(f"Received {len(messages)} message(s)")
                    
                    for message in messages:
                        # Process the message
                        success = self.process_message(message['Body'])
                        
                        if success:
                            # Delete message from queue after successful processing
                            self.sqs.delete_message(
                                QueueUrl=self.queue_url,
                                ReceiptHandle=message['ReceiptHandle']
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
            except Exception as e:
                logger.error(f"Error polling queue: {e}")
                time.sleep(5)  # Wait before retrying
    
    def shutdown(self):
        """Gracefully shutdown the server"""
        logger.info("Shutting down server...")
        self.running = False
    
    def run(self):
        """Start the polling server"""
        logger.info(f"Starting SQS polling server for queue: {self.queue_name}")
        logger.info("Press Ctrl+C to stop")
        
        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, lambda s, f: self.shutdown())
        signal.signal(signal.SIGTERM, lambda s, f: self.shutdown())
        
        # Start polling
        self.poll_queue()
        
        logger.info("Server stopped")


def main():
    """Main entry point"""
    # Configuration from environment variables
    QUEUE_NAME = os.getenv("SQS_QUEUE_NAME", "ai-chaperone-image-processing-queue")
    REGION = os.getenv("AWS_REGION", "us-east-2")

    try:
        # Create and run the server
        server = SQSPollingServer(QUEUE_NAME, REGION)
        server.run()
    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()