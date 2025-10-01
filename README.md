# AI Chaperone - Content Moderation Pipeline

## Overview

AI Chaperone is a comprehensive, serverless content moderation system built on AWS that analyzes both video and transcript content for safety violations. The system uses a multi-layered approach combining rules-based keyword detection with advanced LLM analysis to provide thorough content moderation at scale.

## Architecture

```
┌─────────────┐      ┌──────────────────┐      ┌─────────────────────┐
│   Client    │─────▶│  Entry Point     │─────▶│    DynamoDB        │
│  (API Call) │      │  Lambda          │      │  (Job Tracking)    │
└─────────────┘      └──────────────────┘      └─────────────────────┘
                              │                           │
                    ┌─────────┴─────────┐                │
                    ▼                   ▼                │
           ┌──────────────┐    ┌──────────────┐         │
           │ Rules Queue  │    │ Image Queue  │         │
           │    (SQS)     │    │    (SQS)     │         │
           └──────────────┘    └──────────────┘         │
                    │                   │                │
                    ▼                   ▼                │
        ┌──────────────────┐  ┌──────────────────┐     │
        │ Rules-Based      │  │ Video Processing │     │
        │ Transcript Mod   │  │ Lambda/Server    │     │
        └──────────────────┘  └──────────────────┘     │
                    │                   │                │
                    ▼                   ▼                │
           ┌──────────────┐    ┌──────────────┐        │
           │ Text LLM     │    │               │        │
           │   Queue      │    │   S3 Results  │        │
           └──────────────┘    └──────────────┘        │
                    │                   │                │
                    ▼                   ▼                │
        ┌──────────────────┐           │                │
        │ Text LLM Server  │           │                │
        │ (Summary/Safety) │           │                │
        └──────────────────┘           │                │
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

### Processing Servers

4. **[Text LLM Server](./text-llm-server/)** *(Documentation needed)*
   - Performs advanced LLM-based text analysis
   - Generates content summaries
   - Provides safety assessments

5. **[Image LLM Server](./image-llm-server/)** *(Documentation needed)*
   - Samples frames from videos
   - Performs visual content moderation
   - Detects inappropriate imagery

## Quick Start

### Prerequisites

- AWS Account with appropriate permissions
- Python 3.11+
- Docker (for LLM servers)
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
OUTPUT_BUCKET=ai-chaperone-results
TEXT_LLM_QUEUE_URL=https://sqs.region.amazonaws.com/account/text-llm-queue

# Stream Handler
DYNAMO_TABLE_NAME=ai-chaperone-video-moderation-jobs
```

#### LLM Servers
```bash
# Text/Image LLM Servers
AWS_REGION=us-east-1
OUTPUT_BUCKET=ai-chaperone-results
DYNAMO_TABLE=ai-chaperone-video-moderation-jobs
SQS_QUEUE_URL=https://sqs.region.amazonaws.com/account/queue-name
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

### LLM Servers (ECS/Fargate)

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

## Required AWS Resources

### DynamoDB Table
- **Name**: ai-chaperone-video-moderation-jobs
- **Partition Key**: job_id (String)
- **Streams**: Enabled (New and old images)

### SQS Queues
- Rules processing queue
- Image processing queue
- Text LLM queue
- Dead letter queues for each

### S3 Buckets
- Input bucket for transcripts and videos
- Output bucket for moderation results
- Keywords bucket for rules engine

### IAM Roles
Each Lambda needs appropriate permissions for:
- DynamoDB read/write
- S3 read/write for specific buckets
- SQS send/receive messages
- CloudWatch Logs

## Monitoring

### Key Metrics
- Lambda invocation count and errors
- SQS queue depth and age
- DynamoDB throttles
- S3 request metrics
- Webhook delivery success rate

### CloudWatch Alarms
Set up alarms for:
- High error rates
- Queue message age > 5 minutes
- Lambda timeouts
- DynamoDB capacity issues