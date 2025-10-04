# Image LLM Server

A containerized video content moderation system that uses vision-enabled LLMs to
analyze videos for safety violations and policy issues.

## Contents
* [Overview](#overview)
* [Architecture](#architecture)
* [Prerequisites](#prerequisites)
* [Setup](#setup)
  * [Clone and navigate](#1-clone-and-navigate)
  * [Create environment file](#2-create-environment-file)
  * [Configure (optional)](#3-configure-optional)
* [Deployment](#deployment)
  * [Start services](#start-services)
  * [Check status](#check-status)
  * [Stop services](#stop-services)
* [Configuration](#configuration)
  * [Environment variables](#environment-variables)
  * [AWS credentials](#aws-credentials)
* [Message format](#message-format)
* [Output](#output)
* [Troubleshooting](#troubleshooting)
  * [Model download fails](#model-download-fails)
  * [GPU not detected](#gpu-not-detected)
  * [Worker can't connect to vllm](#worker-cant-connect-to-vllm)
  * [AWS credentials issues](#aws-credentials-issues)
* [Development](#development)
  * [Local testing without Docker](#local-testing-without-docker)
* [Performance](#performance)
* [Scaling](#scaling)
* [Code](#code)
  * [Code outline](#code-outline)
  * [Code overview](#code-overview)
  * [prompts/](#prompts)
  * [utils/](#utils)
    * [file_utils.py](#file_utilspy)
    * [model_utils.py](#model_utilspy)
    * [video_utils.py](#video_utilspy)
  * [model_client.py](#model_clientpy)
  * [aws_server.py](#aws_serverpy)

## Overview

This system consists of two containerized services:

1. **VLLM Inference Server** - GPU-accelerated inference server running the
   Gemma-3 vision model
2. **SQS Worker** - Python application that polls AWS SQS for video moderation
   jobs, samples video frames, and sends them to the LLM for analysis

## Architecture

```
AWS SQS Queue --> Worker Container --> VLLM Container (GPU)
                       |
                       v
                 AWS S3 (results) + DynamoDB (job status)
```

## Prerequisites

- Docker and Docker Compose
- NVIDIA GPU with CUDA support
- [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)
- HuggingFace account with access token (for downloading models)
- AWS credentials (IAM role on EC2 or local credentials)

## Setup

### 1. Clone and Navigate

```bash
cd image-llm-server
```

### 2. Create Environment File

Create a `.env` file in the `image-llm-server` directory:

```bash
# Required: HuggingFace token for model download
HF_TOKEN=your_huggingface_token_here

# Optional: Override default AWS configuration
# AWS_REGION=us-east-2
# QUEUE_NAME=ai-chaperone-image-processing-queue
```

### 3. Configure (Optional)

Edit `docker-compose.yml` to adjust:

- Model selection (`MODEL_ID`)
- GPU memory utilization (`GPU_MEMORY_UTILIZATION`)
- AWS region and queue name
- Port mappings

## Deployment

### Start Services

```bash
docker compose up -d
```

This will:

1. Build both containers
2. Download the Gemma-3 model from HuggingFace (first run only, ~8GB)
3. Start the VLLM inference server
4. Wait for VLLM to be healthy
5. Start the SQS worker

### Check Status

```bash
# View logs from both services
docker compose logs -f

# View logs from specific service
docker compose logs -f vllm
docker compose logs -f worker

# Check service health
docker compose ps
```

### Stop Services

```bash
docker compose down
```

## Configuration

### Environment Variables

**VLLM Service:**

- `MODEL_ID` - HuggingFace model identifier (default: `google/gemma-3-4b-it`)
- `MODEL_DIR` - Directory to store downloaded models (default: `/models`)
- `GPU_MEMORY_UTILIZATION` - GPU memory fraction to use (default: `0.94`)
- `TENSOR_PARALLEL_SIZE` - Number of GPUs for tensor parallelism (default: `1`)
- `HF_TOKEN` - HuggingFace token for model downloads

**Worker Service:**

- `VLLM_URL` - URL of VLLM inference server (default: `http://vllm:8000`)
- `AWS_REGION` - AWS region for SQS/S3/DynamoDB (default: `us-east-2`)
- `QUEUE_NAME` - SQS queue to poll for jobs (default:
  `ai-chaperone-image-processing-queue`)
- `OUTPUT_BUCKET` - S3 bucket for storing results (default: `ai-chaperone-dev`)
- `DYNAMO_TABLE` - DynamoDB table for job tracking (default:
  `ai-chaperone-video-moderation-jobs`)

### AWS Credentials

The worker service expects AWS credentials via:

- **On EC2**: IAM instance role (recommended)
- **Local development**: Mount `~/.aws` or set `AWS_ACCESS_KEY_ID` and
  `AWS_SECRET_ACCESS_KEY` in `.env`

## Message Format

The worker expects SQS messages in this format:

```json
{
  "job_id": "unique-job-identifier",
  "video_s3_url": "s3://bucket-name/path/to/video.mp4"
}
```

## Output

Results are saved to:

- **S3**:
  `s3://ai-chaperone-dev/moderation-results/{job_id}/image_llm_safety_result.json`
- **DynamoDB**: Updates `ai-chaperone-video-moderation-jobs` table with result
  location and completion status

## Troubleshooting

### Model Download Fails

- Verify `HF_TOKEN` is set correctly in `.env`
- Check HuggingFace account has access to the model
- Ensure adequate disk space (~8GB+ for model)

### GPU Not Detected

- Verify NVIDIA Container Toolkit is installed:
  `docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi`
- Check Docker Compose version supports `deploy.resources.reservations`

### Worker Can't Connect to VLLM

- Check VLLM container is healthy: `docker compose ps`
- View VLLM logs: `docker compose logs vllm`
- Verify healthcheck passes: `curl http://localhost:8000/health`

### AWS Credentials Issues

- On EC2: Verify IAM role has permissions for SQS, S3, and DynamoDB
- Locally: Check `~/.aws/credentials` or environment variables are set

## Development

### Local Testing (without Docker)

1. Install dependencies:

```bash
# editable install
pip install -e .
# otherwise
pip install .
```

A requirements.txt file is also included for optional dependency installation
via `pip install -r requirements.txt`

2. Run VLLM server separately

```bash
screen -S vllm-server
export HF_TOKEN="your_huggingface_access_token"
vllm serve google/gemma-3-4b-it # or your model name / path to model
# Ctrl+A D to detach
```

3. Set environment variables and run worker:

```bash
export VLLM_URL=http://localhost:8000
export AWS_REGION=us-east-2
export QUEUE_NAME=your-queue-name
aws-server # python -m core.aws_server also works
```

## Performance

- **Frame sampling**: 1 FPS, max 50 frames per video
- **Processing time**: ~30-60 seconds per video (depends on GPU and video
  length)
- **Throughput**: Single worker can process ~60-120 videos/hour

## Scaling

To scale horizontally:

1. Deploy multiple EC2 instances with this stack
2. All workers poll the same SQS queue
3. SQS automatically distributes messages across workers
4. Use Auto Scaling Group to scale based on queue depth

## Code

### Code outline

```
src/
└── core/                        # Main package
    ├── prompts/                 # Prompt templates directory
    │   ├── system/              # System prompts in markdown format
    │   ├── user/                # User prompts in markdown format
    │   └── config.json          # Configuration for valid categories and prompt types (system, user, json)
    │
    ├── utils/                   # Utility functions directory
    │   ├── __init__.py
    │   ├── file_utils.py        # File handling utility functions
    │   ├── model_utils.py       # Model utility functions with prompts and json schema
    │   └── video_utils.py       # Video frame sampling utilities
    │
    ├── __init__.py
    ├── aws_server.py            # SQS polling server
    └── model_client.py          # Model client to send requests to vllm

pyproject.toml                   # Project configuration and dependencies
```

### Code overview
All code for the video processing element of the AI chaperone lives in `src/core`. The pipeline begins by polling AWS SQS for jobs `aws_server.py`. If there is a job, we process the video, analyze its contents, and save results to S3 and DynamoDB.

### `prompts/`
A folder that contains all the prompts needed for video processing.

#### `config.json`
JSON containing valid prompt types and category types in the following format:

```json
{
    "prompt_types": ["system", "user", "json"], # list of valid prompt types
    "category_types": ["safety"] # list of valid category types
}
```

This structure provides flexibility for incorporating additional processing types in the future, such as delight.

#### `system/`
This folder contains all the system prompts in the format `<category_type>.md`.

#### `user/`
This folder contains all the user prompts in the format `<category_type>.md`.

### `utils/`
Contains all the utility functions for file reading and handling, frame sampling, and model prompting.

### `file_utils.py`
Utilities for loading and validating files with caching.

#### Functions
##### `load_file`
```python
def load_file(
    prompt_type: str,
    category_type: str,
    config_path: str = "prompts/config.json",
    prompts_dir: str = "prompts"
) -> str
```
Loads and caches the prompt file contents.

**Parameters**
* `prompt_type` (str): The prompt type to load (this prompt type must exist in config.json)
* `category_type` (str): The category type to load (this type must exist in config.json)
* `config_path` (str, optional): Path to the JSON config file. Default: "prompts/config.json".
* `prompts_dir` (str, optional): Path to prompts directory. Default: "prompts"

**Returns**
* `str`: The contents of the prompt .md file

**Raises**
* `ValueError`: If prompt_type or category_type is invalid.
* `FileNotFoundError`: If the prompt .md file does not exist in `prompts_dir/<prompt_type>/category_type.md`.

**Notes**
* Results are cached for performance

##### `validate_types`
```python
def validate_types(
    prompt_type: str,
    category_type: str,
    config_path: str = "prompts/config.json"
) -> None
```
Validates that prompt and category types exist in the configuration file.

**Parameters**

* `prompt_type` (str): The prompt type to validate
* `category_type` (str): The category type to validate
* `config_path` (str, optional): Path to JSON config file. Default: "prompts/config.json"

**Raises**

* `ValueError:` If either type is empty or not found in config
* `FileNotFoundError`: If config file doesn't exist

##### `_load_config` (internal)
```python
def _load_config(config_path: str | Path = "prompts/config.json") -> dict
```

Loads and caches the configuration file. Used internally.

**Parameters**

* `config_path` (str | Path, optional): Path to JSON config file. Default: "prompts/config.json"

**Returns**
* `dict`: configuration data with prompt_types and category_types

**Raises**
* `FileNotFoundError`: If config file does not exist

**Notes**
* Cached for performance
* Path is resolved relative to the parent directory of the module

### `model_utils.py`
#### Functions
##### `get_json_schema`
```python
def get_json_schema(output_type: str = "safety") -> dict[str, Any] | None
```
Returns the JSON schema of the response required from the model based on the output_type (category_type).

**Parameters**
* `output_type` (str, optional): The category type. Default: "safety".

**Returns**
* `dict[str, Any] | None`: Pydantic model JSON schema.

**Raises**
* `ValueError`: If output_type is invalid (validated with config.json).

##### `get_system_prompt`
```python
def get_system_prompt(output_type: str = "safety") -> str
```
**Parameters**
* `output_type` (str, optional): The category type. Default: "safety".

**Returns**
* `str`: System prompt content

**Raises**
* `ValueError`: If output_type is invalid (compared to config.json)
* `FileNotFoundError`: If prompt file does not exist.

##### `get_system_schema`
```python
def get_user_prompt(output_type: str = "safety") -> str
```
**Parameters**
* `output_type` (str, optional): The category type. Default: "safety".

**Returns**
* `str`: User prompt content

**Raises**
* `ValueError`: If output_type is invalid (compared to config.json)
* `FileNotFoundError`: If prompt file does not exist.

### `video_utils.py`
Utility functions to extract frames with the most movement.

#### Functions
##### `sample_video_frames`
```python
def sample_video_frames(
    video_path: str,
    fps: int = 2,
    max_frames: int = 10,
    *,
    convert_b64: bool = True
) -> list[Any]
```
Samples frames from a video by selecting those with the largest visual changes

**Parameters**
* `video_path` (str): Path to the video file
* `fps` (int, optional): Target sampling rate in frames per second. Default: 2
* `max_frames` (int, optional): Maximum number of frames to return. Default: 10
* `img_size` tuple(int, int): Image size to resize original frames to for sampling. Default: (512, 288)
* `convert_b64` (bool, optional): Whether to return base64-encoded strings. Default: True

**Returns**

* `list[Any]`: List of base64-encoded JPEG strings (if convert_b64=True) or PIL Images

**Algorithm**

1. Samples video at specified fps
2. Converts frames to grayscale and resizes to img_size (512×288 by default) for performance and reduced memory.
3. Calculates frame-to-frame differences using pixel-wise absolute difference
4. Returns the max_frames with highest visual change

### `model_client.py`
General and minimal HTTP client for interacting with the vLLM server. Will work for any vLLM-compatible servers. 

#### Classes
##### `ModelClient`
```python
class ModelClient:
    def __init__(self, url: str | None = None, timeout: int = 120) -> None
```
**Parameters**
* `url` (str | None, optional): Base URL of the vLLM server. Default: None. If None, uses VLLM_URL environment variable or "http://localhost:8000"

* `timeout` (int, optional): Request timeout in seconds. Default: 120s.

**Attributes**

* `url` (str): Full endpoint URL ({base_url}/v1/chat/completions)
* `timeout` (int): Request timeout

#### Methods
##### `chat_completion`
```python
def chat_completion(
    self,
    messages: list[Any],
    **kwargs: dict[str, Any]
) -> list[Any] | None
```
Sends a chat completion request to the vLLM server.

**Parameters**
* `messages` (list[Any]): List of message objects.
* `**kwargs` (dict[str, Any]): Additional parameters passed to the server. E.g., temperature, max_tokens, top_p, guided_json.

**Returns**
* list[Any] | None: LLM response JSON if successful, None if the request fails.

**Example usage**
```python
messages = [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Describe San Francisco"}
]

# Basic request
response = client.chat_completion(messages)

# With parameters
response = client.chat_completion(
    messages,
    temperature=0.2,
    max_tokens=500
)
```
### `aws_server.py`
#### Classes
##### `SQSPollingServer`
```python
class SQSPollingServer:
    def __init__(self, queue_name: str, region: str = "us-east-2") -> None
```
Server that polls AWS SQS for jobs, processes videos, and stores results in S3.

**Parameters**
* `queue_name` (str): Name of the SQS queue to poll
* `region` (str, optional): AWS region of all services (SQS, DynamoDB, and S3). Default: "us-east-2"

**Attributes**
* `queue_name` (str): SQS queue name
* `region` (str): AWS region
* `running` (bool): Server running state
* `sqs:` Boto3 SQS client
* `s3:` Boto3 S3 client
* `dynamo_table:` Boto3 DynamoDB table resource
* `model_client` ([ModelClient](#model_clientpy)): LLM client instance
* `queue_url` (str): Full SQS queue URL

#### Public methods
##### `run`
```python
def run(self) -> None
```
Runs the polling server and sets up graceful shutdown handlers.

##### `shutdown`
```python
def shutdown(self) -> None
```
Gracefully shuts down the polling server.

##### `poll_queue`
```python
def poll_queue(self) -> None
```
Continuously polls the SQS queue for jobs and processes them.

**Notes**
* Uses long polling (20s wait)
* Processes messages sequentially (1 at a time)
* 60s visibility timeout
* Re-adds the job to the queue if visibility timeout is hit.
* Retries polling with 5s delay if exception occurs.

##### `process_message`
```python
def process_message(self, message_body: str) -> bool
```
Processes SQS message.

**Parameters**
* `message_body` (str): JSON string containing details of the job.

**Returns**
* `bool`: `True` if processing succeeded. `False` otherwise.

**Notes**
Message is expected to have:
```json
{
  "job_id": "unique-job-id",
  "video_s3_url": "s3://bucket/path/to/video.mp4"
}
```

##### `analyze_video_for_issues`
```python
def analyze_video_for_issues(
    self,
    video_path: str,
    fps: int = 1,
    max_frames: int = 50
) -> list[Any] | None
```
Analyzes video for content safety issues by sampling frames, curating the message, and sending a request to the LLM.

**Parameters**
* `video_path` (str): Local path to video file
* `fps` (int, optional): Frames per second for sampling. Default: 1
* `max_frames` (int, optional): Maximum frames to analyze. Default: 50

**Returns**
* `list[Any] | None`: Raw LLM response if successful, None on failure

#### Private methods
##### `_parse_message`
```python
def _parse_message(self, message_body: str) -> dict[str, Any] | None
```
Parses and validates incoming SQS message JSON.

**Returns**
* `dict | None`: Parsed message with job_id and video_s3_url, or None if invalid

##### `_parse_s3_url`
```python
def _parse_s3_url(self, s3_url: str) -> tuple[Any, Any] | tuple[None, None]
```
Extracts the bucket and key from S3 URL.

**Parameters**
* `s3_url` (str): S3 URL in format s3://bucket-name/path/to/object

**Returns**
* `tuple[str, str] | tuple[None, None]`: (bucket, key) or (None, None) if invalid

##### `_download_video`
```python
def _download_video(self, s3_url: str, job_id: str | None = None) -> str | None
```
Downloads video from S3 to temp storage.

**Parameters**
* `s3_url` (str): S3 URL of the video file (format: s3://bucket/key)
* `job_id` (str | None, optional): Unique job id used for naming the local file. Default: None

**Returns**
* `str | None`: Local file path if successful, None otherwise

##### `_parse_llm_response`
```python
def _parse_llm_response(self, response: dict) -> dict[str, Any] | None
```
Validates and extracts JSON content from LLM response.

**Parameters**
* `response` (dict): Raw response from LLM

**Returns**
* `dict | None`: Parsed JSON content, or None if invalid

##### `_save_results_to_s3`
```python
def _save_result_to_s3(
    self,
    job_id: str,
    llm_result: dict[str, Any] | str,
    output_type: str = "safety"
) -> str | None
```
Saves the moderation results json to S3.

**Parameters**
* `job_id` (str): SQS job id
* `llm_result` (dict[str, Any] | str): Analysis results to save (dictionary or JSON string)
* `output_type` (str, optional): Category type. Default: "safety"

**Returns**
* `str | None`: S3 URL (s3://bucket/key) if successful, None otherwise

**Notes**
Current storage path: `s3://{OUTPUT_BUCKET}/moderation-results/{job_id}/image_llm_{output_type}_result.json`

##### `_update_dynamo`
```python
def _update_dynamo(self, job_id: str, result_s3_url: str) -> bool
```
Updates DynamoDB with job completion status and location of results on S3.

**Parameters**
* `job_id` (str): Unique job identifier (DynamoDB primary key)
* `result_s3_url` (str): S3 URL where analysis results are stored

**Returns**
* `bool:` True if update succeeded, False otherwise

**Notes**
Updates the following fields in DynamoDB:
* `video_llm_result_s3_url`: S3 URL of results
* `video_complete`: Set to True
* `updated_at`: ISO timestamp

##### `_build_messages`
```python
def _build_messages(self, request_type: str = "safety") -> list[dict[Any, Any]] | None
```
Builds the message request to send to the LLM.

**Parameters**
* `request_type` (str, optional): Type of analysis to perform or category type (determines which prompts to load). Default: "safety"

**Returns**
* `list | None`: Messages with system and user prompts, or None if error occurs.

##### `_call_llm`
```python
def _call_llm(self, messages: list[dict[Any, Any]]) -> list[Any] | None
```
Calls the LLM through the model client

**Parameters**
* `messages` (list[dict[Any, Any]]): Array of message objects with role and content keys

**Returns**
* `list | None`: Raw LLM response, or None on failure

#### Entry point
##### `main`
```python
def main() -> None
```
Entry point that initializes and runs the server.