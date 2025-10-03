"""Utility imports for client."""
import logging
import os
from typing import Any

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

class ModelClient:
    """Create client to send requests to the vLLM server."""

    def __init__(self, url: str | None= None, timeout: int= 120) -> None:
        """Initialize client."""
        if url is None:
            url = os.getenv("VLLM_URL", "http://localhost:8000")
        self.url = f"{url}/v1/chat/completions"
        self.timeout = timeout
        logger.info("Initialized client for %s", url)

    def chat_completion(self, messages: list[Any], **kwargs: dict[str, Any]) -> list[Any] | None:
        """Send a chat completion request."""
        payload = {
                "messages" : messages,
                **kwargs,
                }

        headers = {
                "Content-Type": "application/json",
                "Authorization": "Bearer no-key",
                }

        try:
            logger.info("Sending chat completion request...")
            response = requests.post(self.url, headers=headers, json=payload, timeout=self.timeout)
            response.raise_for_status()
            result = response.json()
            logger.info("Received response")

        except Exception:
            logger.exception("Request failed")
            return None

        else:
            return result

