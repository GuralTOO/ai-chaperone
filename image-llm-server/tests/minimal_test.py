import argparse  # noqa: D100, INP001
import logging
import sys
from typing import Any

from core.model_client import ModelClient
from core.utils.model_utils import get_json_schema, get_system_prompt, get_user_prompt
from core.utils.video_utils import sample_video_frames

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

def analyze_video_for_issues(video_path: str, fps: int=1,  max_frames: int=50) -> list[Any] | None:
    """Analyze a video for any issues by sampling frames and sending them to the model."""
    client = ModelClient()

    try:
        # Sample frames from the video
        logger.info("Sampling frames from video: %s", video_path)
        sampled_images = sample_video_frames(video_path, fps=fps, max_frames=max_frames)

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
        response = client.chat_completion(messages, temperature=0.1, extra_body={"guided_json": get_json_schema()})

        if not response:
            logger.error("No response received from model")
            return None

    except Exception:
        logger.exception("Error analyzing video")
        return None
    else:
      logger.info("Analysis completed successfully")
      return response


def main() -> None:
    """Run video analysis."""
    parser = argparse.ArgumentParser(description="Analyze video frames for issues")
    parser.add_argument("--video-path", help="Path to the video file to analyze", default="data/videos/my_video.mp4")

    args = parser.parse_args()

    response = analyze_video_for_issues(args.video_path)

    if response:
        logger.info(response)
    else:
        logger.error("Failed to analyze video", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
