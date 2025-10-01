# AI Chaperone Stream Handler Lambda Function

## Overview
This Lambda function monitors DynamoDB Streams to detect when both transcript and video processing pipelines have completed for a job. Once both branches finish, it aggregates the results, determines the highest severity levels, and sends a webhook notification to the client with the final moderation results.

## Purpose
The function serves as the final orchestrator in the content moderation pipeline by:
1. Monitoring DynamoDB stream events for job status changes
2. Detecting when both processing branches (transcript and video) complete
3. Fetching and aggregating results from multiple S3 locations
4. Calculating overall severity levels
5. Sending webhook notifications with final results
6. Marking jobs as fully combined/completed

## Trigger Configuration
This function is triggered by DynamoDB Streams with:
- **Event Source**: DynamoDB table stream
- **Starting Position**: LATEST or TRIM_HORIZON
- **Batch Size**: Recommended 1-10 records
- **Event Types**: INSERT, MODIFY, REMOVE (function filters for MODIFY)

## Environment Variables
Required:
- `DYNAMO_TABLE_NAME`: Name of the DynamoDB table for job tracking

## Processing Logic

### Event Detection
The function specifically looks for MODIFY events where:
- Both `transcript_complete` and `video_complete` transition to `true`
- The `combined` flag is still `false`
- This ensures each job is processed exactly once

### Completion Detection Algorithm
```python
was_incomplete = not (old_transcript and old_video)
is_complete = new_transcript and new_video
if was_incomplete and is_complete and not combined:
    # Process the completed job
```

## Severity Level System
The function uses a hierarchical severity system:
```python
SEVERITY_LEVELS = {
    'SAFE': 0,
    'LOW': 1,
    'MEDIUM': 2,
    'HIGH': 3
}
```

### Severity Aggregation
- **Transcript Severity**: Maximum of rules-based and LLM safety results
- **Video Severity**: From image/video LLM analysis
- Each result file's `highest_severity_level` field is compared
- The highest severity across all files is reported

## Webhook Payload Format
When both pipelines complete, the function sends:
```json
{
  "job_id": "uuid-string",
  "transcript_highest_severity_level": "HIGH",
  "video_highest_severity_level": "MEDIUM",
  "rules_result_url": "s3://bucket/moderation-results/job-id/rules_result.json",
  "llm_safety_result_url": "s3://bucket/moderation-results/job-id/llm_safety_result.json",
  "llm_summary_result_url": "s3://bucket/moderation-results/job-id/llm_summary_result.json",
  "image_llm_safety_result_url": "s3://bucket/moderation-results/job-id/image_llm_result.json"
}
```

## Webhook Delivery

### Retry Logic
- **Max Attempts**: 3
- **Backoff Strategy**: Exponential (1s, 2s, 4s delays)
- **Timeout**: 5 seconds connection, 10 seconds read
- **Success Criteria**: HTTP status 200-299

### Error Handling
- Invalid or missing webhook URLs are handled gracefully
- Jobs without webhooks are marked as combined without notification
- Failed webhooks after retries do NOT mark job as combined (allows manual retry)

## S3 File Processing
The function fetches and validates JSON files from S3:
1. Parses S3 URLs to extract bucket and key
2. Downloads and parses JSON content
3. Handles malformed JSON gracefully
4. Extracts `highest_severity_level` from each file

## DynamoDB Updates
Upon successful webhook delivery:
- Sets `combined = true`
- Updates `status = 'COMPLETE'`
- Records `updated_at` timestamp

## Data Flow
```
DynamoDB Stream Event (MODIFY)
    ↓
Check if both pipelines complete
    ↓
Fetch results from S3:
  - transcript_rules_result_s3_url
  - transcript_llm_safety_result_s3_url
  - transcript_llm_summary_result_s3_url
  - video_llm_result_s3_url
    ↓
Calculate severity levels
    ↓
Send webhook notification
    ↓
Update DynamoDB (combined=true)
```

## Error Scenarios

### Handled Gracefully
- Missing or invalid webhook URLs (job marked complete without notification)
- Malformed JSON in S3 files (defaults to SAFE severity)
- S3 access errors (continues with available data)
- Webhook timeouts (retries with exponential backoff)

### Critical Failures
- DynamoDB update failures (logged but doesn't block processing)
- Missing job_id in stream record (record skipped)

## Performance Considerations
- **Stream Processing**: Handles batches of 1-10 records efficiently
- **S3 Operations**: Parallel fetching when possible
- **Webhook Calls**: Asynchronous with connection pooling
- **Memory**: 256MB typically sufficient
- **Timeout**: Set to at least 60 seconds for webhook retries

## AWS Permissions Required
- **DynamoDB**:
  - Stream read permissions on source table
  - `dynamodb:UpdateItem` on job tracking table
- **S3**: `s3:GetObject` on result buckets
- **Network**: Outbound HTTPS for webhooks

## Monitoring and Metrics

### Key Metrics to Track
- **Stream Iterator Age**: Monitor for processing delays
- **Webhook Success Rate**: Track delivery failures
- **Processing Latency**: Time from completion to webhook
- **Error Rate**: Failed S3 fetches or DynamoDB updates

### CloudWatch Logs
The function provides detailed logging:
- Job processing status
- Webhook attempt details
- Severity calculation results
- Error messages with context

## Testing

### Test Event Format
```json
{
  "Records": [
    {
      "eventName": "MODIFY",
      "dynamodb": {
        "OldImage": {
          "job_id": {"S": "test-123"},
          "transcript_complete": {"BOOL": false},
          "video_complete": {"BOOL": true}
        },
        "NewImage": {
          "job_id": {"S": "test-123"},
          "transcript_complete": {"BOOL": true},
          "video_complete": {"BOOL": true},
          "combined": {"BOOL": false},
          "webhook_url": {"S": "https://example.com/webhook"},
          "transcript_rules_result_s3_url": {"S": "s3://bucket/path/rules.json"},
          "transcript_llm_safety_result_s3_url": {"S": "s3://bucket/path/safety.json"},
          "transcript_llm_summary_result_s3_url": {"S": "s3://bucket/path/summary.json"},
          "video_llm_result_s3_url": {"S": "s3://bucket/path/video.json"}
        }
      }
    }
  ]
}
```

## Best Practices
1. **Idempotency**: The `combined` flag ensures each job is processed once
2. **Webhook Security**: Validate webhook URLs before calling
3. **Graceful Degradation**: Continue processing even if some files are missing
4. **Retry Strategy**: Exponential backoff prevents overwhelming webhook endpoints
5. **Monitoring**: Set up alarms for high stream iterator age

## Integration Points
- **Input**: DynamoDB Streams from job tracking table
- **S3 Results**: Reads moderation results from multiple processors
- **Webhook Delivery**: Notifies client applications
- **Job Status**: Updates final status in DynamoDB

## Troubleshooting

### Common Issues
1. **Webhooks not being called**: Check webhook_url validity and network connectivity
2. **Jobs stuck uncombined**: Verify both pipelines are completing successfully
3. **High latency**: Check stream batch size and Lambda concurrency
4. **Missing results**: Ensure S3 URLs are correctly stored in DynamoDB

### Debug Steps
1. Check CloudWatch logs for specific job_id
2. Verify DynamoDB record has all required fields
3. Test S3 file accessibility
4. Validate webhook endpoint manually
5. Check Lambda execution role permissions