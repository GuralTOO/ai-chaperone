# Image LLM Server

A containerized video content moderation system that uses vision-enabled LLMs to
analyze videos for safety violations and policy issues.

## Overview

This system consists of two containerized services:

1. **VLLM Inference Server** - GPU-accelerated inference server running the
   Gemma-3 vision model
2. **SQS Worker** - Python application that polls AWS SQS for video moderation
   jobs, samples video frames, and sends them to the LLM for analysis

## Architecture

```
AWS SQS Queue � Worker Container � VLLM Container (GPU)
                      �
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
docker-compose up -d
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
docker-compose logs -f

# View logs from specific service
docker-compose logs -f vllm
docker-compose logs -f worker

# Check service health
docker-compose ps
```

### Stop Services

```bash
docker-compose down
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

- Check VLLM container is healthy: `docker-compose ps`
- View VLLM logs: `docker-compose logs vllm`
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
A requirements.txt file is also included for optional dependency installation via `pip install -r requirements.txt`

2. Run VLLM server separately
   
```bash
screen -S vllm-server
export HF_TOKEN="your_huggingface_access_token"
vllm serve google/gemma-3-4b-it # or your model name / path to model
# Ctrl+A D to detach
```

4. Set environment variables and run worker:

```bash
export VLLM_URL=http://localhost:8000
export AWS_REGION=us-east-2
export QUEUE_NAME=your-queue-name
python -m core.aws_server
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
