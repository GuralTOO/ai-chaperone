from core.model_client import ModelClient
from core.utils.model_utils import get_system_prompt, get_user_prompt, get_json_schema
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

def get_args():
    parser = argparse.ArgumentParser(description="Process data to model")
    parser.add_argument("--file", default="/mnt/models/gemma-3-code/data/transcript_1.txt",
    help="Path to data")
    parser.add_argument("--output-type", default="safety", help="Type of output: summary or safety")
    parser.add_argument("--temperature", type=float, default=0.3, help="Temperature for model")

    args = parser.parse_args()
    return args

def main():
    args = get_args()
    client = ModelClient()
    output_type = args.output_type

    with open(args.file, "r", encoding="utf-8") as f:
        data = f.read()

    user_prompt = get_user_prompt(data, type=output_type) 

    messages = [
            {
                "role": "system",
                "content": get_system_prompt(type=output_type)
            },
            {
                "role": "user",
                "content": user_prompt
            }
        ]

    json_schema = get_json_schema(output_type=output_type)
    response = client.chat_completion(messages, temperature=0.3, extra_body={'guided_json': json_schema})
    print(response)
    return response 

if __name__ == "__main__":
    main()
