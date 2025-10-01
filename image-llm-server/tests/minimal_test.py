from core.model_client import ModelClient
from core.utils.model_utils import get_system_prompt, get_user_prompt, get_json_schema
from core.utils.video_utils import sample_video_frames 
import json
import argparse
import sys
import time
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def analyze_video_for_issues(video_path, fps=1,  max_frames=50):
    """
    Analyze a video for any issues by sampling frames and sending them to the model.
    
    Args:
        video_path (str): Path to the video file to analyze
    
    Returns:
        str: Model response about any issues found in the video frames
    """
    client = ModelClient()
    
    try:
        # Sample frames from the video
        logger.info(f"Sampling frames from video: {video_path}")
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
        response = client.chat_completion(messages, temperature=0.1, extra_body={"guided_json": get_json_schema()})
        
        if response:
            logger.info("Analysis completed successfully")
            return response
        else:
            logger.error("No response received from model")
            return None
            
    except Exception as e:
        logger.error(f"Error analyzing video: {str(e)}")
        return None

def main():
    """Main function to handle command line arguments and run video analysis"""
    parser = argparse.ArgumentParser(description="Analyze video frames for issues")
    parser.add_argument("--video-path", help="Path to the video file to analyze", default="data/videos/my_video.mp4")
    
    args = parser.parse_args()
    
    response = analyze_video_for_issues(args.video_path)
    
    if response:
        print(response)
    else:
        print("Failed to analyze video", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
