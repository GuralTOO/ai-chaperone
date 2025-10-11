# AI Chaperone Entry Point Lambda Function

## Overview
This Lambda function serves as the entry point for the AI Chaperone content moderation pipeline. It accepts video and transcript files stored in S3, validates them, creates a job tracking entry, and initiates parallel processing workflows for both transcript and video analysis.

## Purpose
The function orchestrates the beginning of a content moderation workflow by:
1. Validating input files exist in S3
2. Creating a unique job ID for tracking
3. Storing job metadata in DynamoDB
4. Triggering parallel processing pipelines via SQS queues

## Input Format
The function expects a JSON payload with the following structure:
```json
{
  "transcript_s3_url": "s3://bucket/path/to/transcript.txt",
  "video_s3_url": "s3://bucket/path/to/video.mp4",
  "webhook_url": "https://your-callback-url.com/webhook",
  "metadata": {}
}
```

### Required Fields
- `transcript_s3_url`: S3 URL to the transcript file
- `video_s3_url`: S3 URL to the video file

### Optional Fields
- `webhook_url`: URL for receiving processing completion notifications
- `metadata`: Additional metadata to associate with the job

## Environment Variables
The function requires the following environment variables:
- `DYNAMO_TABLE_NAME`: Name of the DynamoDB table for job tracking
- `RULES_QUEUE_URL`: SQS queue URL for transcript rules-based processing
- `IMAGE_QUEUE_URL`: SQS queue URL for video/image processing

## Processing Flow
1. **Validation**: Verifies that both S3 files exist and are accessible
2. **Job Creation**: Generates a unique UUID for the job and creates a DynamoDB entry with initial status
3. **Queue Messages**: Sends messages to two SQS queues:
   - Rules queue for transcript analysis
   - Image queue for video frame extraction and analysis
4. **Response**: Returns the job ID to the client for tracking

## DynamoDB Schema
The function creates job entries with the following attributes:
- `job_id`: Unique identifier for the job
- `status`: Current processing status (initially "PROCESSING")
- `transcript_complete`: Boolean flag for transcript processing completion
- `video_complete`: Boolean flag for video processing completion
- `combined`: Boolean flag for combined analysis completion
- `transcript_s3_url`: Input transcript location
- `video_s3_url`: Input video location
- `webhook_url`: Callback URL for notifications
- `transcript_rules_result_s3_url`: Output location for rules-based results
- `transcript_llm_summary_result_s3_url`: Output location for LLM summary
- `transcript_llm_safety_result_s3_url`: Output location for LLM safety analysis
- `video_llm_result_s3_url`: Output location for video analysis results
- `metadata`: User-provided metadata
- `created_at`: Timestamp of job creation
- `updated_at`: Timestamp of last update

## Response Format

### Success Response (200)
```json
{
  "job_id": "uuid-string",
  "status": "PROCESSING",
  "message": "Job queued successfully"
}
```

### Error Responses

#### 400 - Bad Request
- Missing required fields
- Invalid S3 URL format
- S3 files not found or inaccessible

#### 500 - Internal Server Error
- DynamoDB operation failures
- SQS message sending failures
- Unexpected errors

## AWS Permissions Required
- **S3**: `s3:GetObject`, `s3:HeadObject` on input buckets
- **DynamoDB**: `dynamodb:PutItem` on the job tracking table
- **SQS**: `sqs:SendMessage` on both processing queues

## Error Handling
The function implements comprehensive error handling:
- Validates S3 URL format before attempting access
- Checks file existence using HEAD requests to minimize data transfer
- Returns descriptive error messages for debugging
- Logs errors for CloudWatch monitoring

## Integration Points
This entry point integrates with:
1. **Transcript Processing Pipeline**: Via RULES_QUEUE_URL
2. **Video Processing Pipeline**: Via IMAGE_QUEUE_URL
3. **Job Status Tracking**: Via DynamoDB table
4. **Client Notifications**: Via webhook_url (processed by downstream services)

## Usage Example
```bash
curl -X POST https://your-api-gateway-url/process \
  -H "Content-Type: application/json" \
  -d '{
    "transcript_s3_url": "s3://my-bucket/transcripts/video123.txt",
    "video_s3_url": "s3://my-bucket/videos/video123.mp4",
    "webhook_url": "https://myapp.com/webhooks/moderation"
  }'
```

## Monitoring
Key metrics to monitor:
- Lambda invocation count and errors
- DynamoDB write throttles
- SQS message send failures
- S3 access errors
- Processing latency