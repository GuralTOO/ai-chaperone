# AI Chaperone - Content Moderation Pipeline

## Overview

AI Chaperone is a comprehensive, serverless content moderation system built on
AWS that analyzes both video and transcript content for safety violations. The
system uses a multi-layered approach combining rules-based keyword detection
with advanced LLM analysis to provide thorough content moderation at scale.

## Architecture

```
┌─────────────┐      ┌──────────────────┐      ┌─────────────────────┐
│   Client    │─────▶│  Entry Point     │─────▶│    DynamoDB         │
│  (API Call) │      │  Lambda          │      │  (Job Tracking)     │
└─────────────┘      └──────────────────┘      └─────────────────────┘
                              │                           │
                    ┌─────────┴─────────┐                 │
                    ▼                   ▼                 │
           ┌──────────────┐    ┌──────────────┐           │
           │ Rules Queue  │    │ Image Queue  │           │
           │    (SQS)     │    │    (SQS)     │           │
           └──────────────┘    └──────────────┘           │
                    │                   │                 │
                    ▼                   ▼                 │
        ┌──────────────────┐  ┌──────────────────┐        │
        │ Rules-Based      │  │ Video Processing │        │
        │ Transcript Mod   │  │ Lambda/Server    │        │
        └──────────────────┘  └──────────────────┘        │
                    │                   │                 │
                    ▼                   ▼                 │
           ┌──────────────┐    ┌──────────────┐           │
           │ Text LLM     │    │              │           │
           │   Queue      │    │   S3 Results │           │
           └──────────────┘    └──────────────┘           │
                    │                   │                 │
                    ▼                   ▼                 │
        ┌──────────────────┐            │                 │
        │ Text LLM Server  │            │                 │
        │ (Summary/Safety) │            │                 │
        └──────────────────┘            │                 │
                    │                   │                │
                    └───────────────────┘                │
                                │                        │
                                ▼                        ▼
                        ┌──────────────┐      ┌──────────────────┐
                        │ S3 Results   │      │ DynamoDB Streams │
                        └──────────────┘      └──────────────────┘
                                                        │
                                                        ▼
                                              ┌──────────────────┐
                                              │ Stream Handler   │
                                              │    Lambda        │
                                              └──────────────────┘
                                                        │
                                                        ▼
                                              ┌──────────────────┐
                                              │ Client Webhook   │
                                              └──────────────────┘
```

## Components

### Lambda Functions

1. **[Entry Point](./lambdas/ai-chaperone-entry-point/README.md)**
   - Validates input files
   - Creates job tracking entries
   - Triggers parallel processing pipelines

2. **[Rules-Based Transcript Moderation](./lambdas/ai-chaperone-rules-based-transcript-moderation/README.md)**
   - High-performance keyword detection using Aho-Corasick algorithm
   - Categorizes violations by severity
   - Processes VTT format transcripts

3. **[Stream Handler](./lambdas/ai-chaperone-stream-handler/README.md)**
   - Monitors job completion via DynamoDB Streams
   - Aggregates results from all processors
   - Sends webhook notifications

### Processing Servers (Containerized)

4. **[Text LLM Server](./text-llm-server/README.md)**
   - GPU-accelerated inference using Google Gemma-3 text model
   - Performs advanced LLM-based transcript analysis
   - Generates content summaries and safety assessments
   - Processes ~120-180 transcripts/hour

5. **[Image LLM Server](./image-llm-server/README.md)**
   - GPU-accelerated inference using Google Gemma-3 vision model
   - Samples frames with highest visual changes (1 FPS, max 50 frames)
   - Performs visual content moderation
   - Processes ~20-30 videos/hour

## Quick Start

### Prerequisites

- AWS Account with appropriate permissions
- Python 3.11+ (for Lambda functions)
- Docker and Docker Compose (for LLM servers)
- NVIDIA GPU with CUDA support (for LLM servers)
- [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)
- HuggingFace account with access token (for model downloads)
- AWS CLI configured

### Environment Variables

#### Lambda Functions

```bash
# Entry Point
DYNAMO_TABLE_NAME=ai-chaperone-video-moderation-jobs
RULES_QUEUE_URL=https://sqs.region.amazonaws.com/account/rules-queue
IMAGE_QUEUE_URL=https://sqs.region.amazonaws.com/account/image-queue

# Rules-Based Moderation
BAD_KEYWORDS_PATH=s3://bucket/keywords.csv
OUTPUT_BUCKET=ai-chaperone-dev
TEXT_LLM_QUEUE_URL=https://sqs.region.amazonaws.com/account/text-llm-queue
DYNAMO_TABLE_NAME=ai-chaperone-video-moderation-jobs
RULES_QUEUE_URL=https://sqs.region.amazonaws.com/account/rules-queue

# Stream Handler
DYNAMO_TABLE_NAME=ai-chaperone-video-moderation-jobs
```

#### LLM Servers (Containerized)

```bash
# Text LLM Server
VLLM_URL=http://vllm:8000
AWS_REGION=us-east-2
QUEUE_NAME=ai-chaperone-text-llm-queue
OUTPUT_BUCKET=ai-chaperone-dev
DYNAMO_TABLE=ai-chaperone-video-moderation-jobs
MODEL_ID=google/gemma-3-4b-it
GPU_MEMORY_UTILIZATION=0.94
HF_TOKEN=your_huggingface_token

# Image LLM Server
VLLM_URL=http://vllm:8000
AWS_REGION=us-east-2
QUEUE_NAME=ai-chaperone-image-processing-queue
OUTPUT_BUCKET=ai-chaperone-dev
DYNAMO_TABLE=ai-chaperone-video-moderation-jobs
MODEL_ID=google/gemma-3-4b-it
GPU_MEMORY_UTILIZATION=0.94
HF_TOKEN=your_huggingface_token
```

## API Usage

### Submit Content for Moderation

```bash
POST /process
Content-Type: application/json

{
  "transcript_s3_url": "s3://bucket/path/to/transcript.vtt",
  "video_s3_url": "s3://bucket/path/to/video.mp4",
  "webhook_url": "https://your-app.com/moderation-complete",
  "metadata": {
    "user_id": "12345",
    "content_id": "abc123"
  }
}
```

### Response

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "processing",
  "message": "Job queued successfully"
}
```

### Webhook Callback

When processing completes, your webhook receives:

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "transcript_highest_severity_level": "HIGH",
  "video_highest_severity_level": "MEDIUM",
  "rules_result_url": "s3://bucket/results/job-id/rules_result.json",
  "llm_safety_result_url": "s3://bucket/results/job-id/llm_safety_result.json",
  "llm_summary_result_url": "s3://bucket/results/job-id/llm_summary_result.json",
  "image_llm_safety_result_url": "s3://bucket/results/job-id/image_llm_result.json"
}
```

## Severity Levels

- **SAFE**: No violations detected
- **LOW**: Minor violations that may not require action
- **MEDIUM**: Moderate violations requiring review
- **HIGH**: Serious violations requiring immediate action

## Deployment

### Lambda Functions

Each Lambda function can be deployed using the AWS CLI:

```bash
# Package and deploy Entry Point
cd lambdas/ai-chaperone-entry-point
zip -r function.zip .
aws lambda update-function-code --function-name ai-chaperone-entry-point --zip-file fileb://function.zip

# Deploy Rules-Based Moderation (includes compiled dependencies)
cd lambdas/ai-chaperone-rules-based-transcript-moderation
zip -r function.zip .
aws lambda update-function-code --function-name ai-chaperone-rules-moderation --zip-file fileb://function.zip

# Deploy Stream Handler
cd lambdas/ai-chaperone-stream-handler
zip -r function.zip .
aws lambda update-function-code --function-name ai-chaperone-stream-handler --zip-file fileb://function.zip
```

### LLM Servers (Docker Compose or ECS/Fargate)

#### Option 1: Docker Compose (Development/Single Instance)

```bash
# Text LLM Server
cd text-llm-server
# Create .env file with HF_TOKEN=your_token
docker compose up -d

# Image LLM Server
cd image-llm-server
# Create .env file with HF_TOKEN=your_token
docker compose up -d
```

#### Option 2: ECS/Fargate (Production)

```bash
# Build and push Docker images
cd text-llm-server
docker build -t ai-chaperone-text-llm .
docker tag ai-chaperone-text-llm:latest $ECR_URI/ai-chaperone-text-llm:latest
docker push $ECR_URI/ai-chaperone-text-llm:latest

cd ../image-llm-server
docker build -t ai-chaperone-image-llm .
docker tag ai-chaperone-image-llm:latest $ECR_URI/ai-chaperone-image-llm:latest
docker push $ECR_URI/ai-chaperone-image-llm:latest
```

Note: LLM servers will automatically download models (~8GB) on first run.

## Infrastructure Details

### AWS Resources Overview

This section consolidates the infrastructure requirements based on information
from component documentation.

### DynamoDB Table

**Table: `ai-chaperone-video-moderation-jobs`**

- **Partition Key**: job_id (String)
- **DynamoDB Streams**: Must be enabled with "New and old images" view type
- **Purpose**: Tracks job status and metadata throughout processing
- **Key Attributes**:
  - `job_id`: Unique identifier
  - `status`: Processing status
  - `transcript_complete`: Boolean flag
  - `video_complete`: Boolean flag
  - `combined`: Boolean flag
  - `transcript_s3_url`: Input location
  - `video_s3_url`: Input location
  - `webhook_url`: Callback URL
  - Result URLs for various processors
  - `created_at` / `updated_at`: Timestamps

### SQS Queues

**1. Rules Processing Queue**

- **Default Name**: `ai-chaperone-rules-queue`
- **Purpose**: Triggers rules-based transcript moderation
- **Recommended Settings**:
  - Batch size: 1 (for reliable processing)

**2. Image Processing Queue**

- **Default Name**: `ai-chaperone-image-processing-queue`
- **Purpose**: Triggers video frame analysis
- **Settings**:
  - Visibility timeout: 60 seconds
  - Long polling: 20 seconds wait time
  - Processes 1 message at a time

**3. Text LLM Queue**

- **Default Name**: `ai-chaperone-text-llm-queue`
- **Purpose**: Triggers LLM transcript analysis
- **Settings**:
  - Visibility timeout: 60 seconds
  - Long polling: 20 seconds wait time
  - Processes 1 message at a time

### S3 Buckets

**1. Input Bucket(s)**

- Stores source video files (MP4 format)
- Stores source transcript files (VTT format)

**2. Keywords Bucket**

- Contains keywords CSV file for rules engine
- **CSV Format**:
  ```csv
  cleaned_words,mod_categories,mod_critical
  "bad word","['violence', 'harassment']","HIGH"
  "inappropriate phrase","['adult_content']","MEDIUM"
  ```

**3. Output Bucket**

- **Default Name**: `ai-chaperone-dev`
- **Result Structure**:
  ```
  moderation-results/
  └── {job_id}/
      ├── rules_result.json
      ├── llm_safety_result.json
      ├── llm_summary_result.json
      └── image_llm_safety_result.json
  ```

### Lambda Functions

**1. Entry Point Lambda**

- **Function Name**: `ai-chaperone-entry-point`
- **Purpose**: API endpoint, validates files, creates jobs
- **Triggers**: API Gateway
- **Memory**: Not specified (recommend 256MB minimum)
- **Timeout**: Not specified (recommend 30 seconds)

**2. Rules-Based Moderation Lambda**

- **Function Name**: `ai-chaperone-rules-moderation`
- **Purpose**: Keyword-based transcript screening
- **Runtime**: Python 3.11+
- **Dependencies**: Requires pyahocorasick (compiled dependency)
- **Memory**: Recommend 512MB-1GB for optimal performance
- **Timeout**: Recommend 5-10 minutes for large transcripts
- **Triggers**: SQS Rules Queue

**3. Stream Handler Lambda**

- **Function Name**: `ai-chaperone-stream-handler`
- **Purpose**: Monitors completion and sends webhooks
- **Memory**: 256MB typically sufficient
- **Timeout**: At least 60 seconds (for webhook retries)
- **Triggers**: DynamoDB Streams
- **Stream Settings**:
  - Starting position: LATEST or TRIM_HORIZON
  - Batch size: 1-10 records

### IAM Permissions Required

**Lambda Functions need:**

- DynamoDB: `PutItem`, `UpdateItem` on job table
- S3: `GetObject`, `HeadObject` on input buckets
- S3: `PutObject` on output bucket
- SQS: `SendMessage`, `ReceiveMessage`, `DeleteMessage` on relevant queues
- CloudWatch Logs: Write permissions
- DynamoDB Streams: Read permissions (for Stream Handler)

**LLM Servers (ECS/EC2) need:**

- S3: `GetObject` on input buckets, `PutObject` on output bucket
- SQS: `ReceiveMessage`, `DeleteMessage` on their respective queues
- DynamoDB: `UpdateItem` on job table

## Performance

### Processing Times

- **Rules-Based Moderation**: < 30 seconds for hour-long transcripts
  - Keyword loading: ~1-2 seconds for thousands of keywords
  - Transcript parsing: ~100-500 utterances/second
  - Pattern matching: ~1000+ utterances/second
- **Text LLM Server**: ~20-30 seconds per transcript
  - Throughput: ~120-180 transcripts/hour per worker
- **Image LLM Server**: ~120-180 seconds per video
  - Frame sampling: 1 FPS, max 50 frames
  - Throughput: ~20-30 videos/hour per worker

## Scaling

### Lambda Functions

- Automatically scale based on incoming requests
- Configure reserved concurrency to control costs
- Use SQS batch size of 1 for reliable processing

### LLM Servers

To scale horizontally:

1. Deploy multiple EC2 instances with GPU support
2. All workers poll the same SQS queue
3. SQS automatically distributes messages across workers
4. Use Auto Scaling Group to scale based on queue depth

## Monitoring

### Key Metrics

- Lambda invocation count and errors
- SQS queue depth and age
- DynamoDB throttles
- S3 request metrics
- Webhook delivery success rate
- GPU utilization (for LLM servers)
- Container health status

### CloudWatch Alarms

Set up alarms for:

- High error rates
- Queue message age > 5 minutes
- Lambda timeouts
- DynamoDB capacity issues
- LLM server health check failures
