import requests
import json
import logging
import os

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

class ModelClient():
    def __init__(self, url=None, timeout=120):
        if url is None:
            url = os.getenv("VLLM_URL", "http://localhost:8000")
        self.url = f"{url}/v1/chat/completions"
        self.timeout = timeout
        logger.info(f"Initialized client for {url}")

    def chat_completion(self, messages, **kwargs):
        """
        Sends a chat completion request
        """

        payload = {
                "messages" : messages,
                **kwargs
                }

        headers = {
                "Content-Type": "application/json",
                "Authorization": "Bearer no-key"
                }

        try:
            logger.info(f"Sending chat completion request...")
            response = requests.post(self.url, headers=headers, json=payload, timeout=self.timeout)
            response.raise_for_status()
            result = response.json()
            logger.info(f"Received response")
            return result

        except Exception as e:
            logger.error(f"Request failed: {e}")
            return None

