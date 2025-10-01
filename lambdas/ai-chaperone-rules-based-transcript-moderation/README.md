# AI Chaperone Rules-Based Transcript Moderation Lambda Function

## Overview
This Lambda function performs high-performance, rules-based content moderation on video transcripts. It uses an optimized Aho-Corasick algorithm to efficiently detect prohibited keywords and phrases in VTT (WebVTT) format transcripts, categorizes violations by severity, and generates detailed moderation reports.

## Purpose
The function provides rapid keyword-based transcript screening by:
1. Downloading transcripts and keyword lists from S3
2. Parsing VTT-formatted transcripts into utterances
3. Detecting violations using optimized pattern matching
4. Categorizing and scoring violations by severity
5. Generating comprehensive moderation reports
6. Triggering downstream LLM-based analysis

## Key Components

### Main Handler (`lambda_handler.py`)
- Processes SQS messages from the entry-point function
- Manages S3 file operations and result uploads
- Updates job status in DynamoDB
- Forwards jobs to LLM processing queue

### Moderation Engine (`transcript_moderation_optimized.py`)
- **KeywordMatcher**: Implements Aho-Corasick automaton for O(n) pattern matching
- **TranscriptParser**: Parses VTT format into structured utterances
- **ModerationEngine**: Orchestrates the moderation process

## Input Format
The function expects an SQS message with the following structure:
```json
{
  "job_id": "c45eb5bd-1b13-4689-a770-3fcd83439264",
  "transcript_s3_url": "s3://bucket/path/to/transcript.vtt"
}
```

## Environment Variables
Required environment variables:
- `BAD_KEYWORDS_PATH`: S3 URL to CSV file containing prohibited keywords
- `DYNAMO_TABLE_NAME`: DynamoDB table name for job tracking
- `OUTPUT_BUCKET`: S3 bucket for storing moderation results
- `RULES_QUEUE_URL`: SQS queue URL for rules processing (self-reference)
- `TEXT_LLM_QUEUE_URL`: SQS queue URL for downstream LLM processing

## Keywords CSV Format
The keywords CSV file should contain:
```csv
cleaned_words,mod_categories,mod_critical
"bad word","['violence', 'harassment']","HIGH"
"inappropriate phrase","['adult_content']","MEDIUM"
```

### Fields:
- `cleaned_words`: The keyword or phrase to detect
- `mod_categories`: Python list format of violation categories
- `mod_critical`: Severity level (LOW, MEDIUM, HIGH)

## Processing Algorithm

### Aho-Corasick Implementation
- **Efficiency**: O(n + m + z) where n=text length, m=total pattern length, z=matches
- **Single-pass**: Processes entire transcript in one scan
- **Word boundaries**: Intelligently handles single words vs phrases
- **Case-insensitive**: Normalizes text for matching

### Performance Optimizations
1. **Batch Processing**: Processes utterances in streaming fashion
2. **Progress Tracking**: Logs progress every 10 seconds for long transcripts
3. **Memory Efficiency**: Uses temporary directories for file handling
4. **Compiled Regex**: Pre-compiles boundary checking patterns

## Output Format
The function generates a JSON report with:
```json
{
  "job_id": "uuid",
  "transcript_file": "path/to/transcript.vtt",
  "transcript_s3_url": "s3://...",
  "processed_at": "2024-01-01T00:00:00",
  "total_utterances": 500,
  "total_violations": 15,
  "compound_severity_score": 85,
  "highest_severity_level": "HIGH",
  "violations": [
    {
      "keyword": "prohibited term",
      "speaker": "Speaker Name",
      "text": "Full utterance containing the term",
      "timestamp": "00:01:23.456",
      "categories": ["category1", "category2"],
      "severity": "HIGH"
    }
  ],
  "speakers_with_violations": ["Speaker1", "Speaker2"],
  "category_report": {
    "violence": {
      "count": 5,
      "violations": [...],
      "speakers": ["Speaker1"]
    }
  }
}
```

## Severity Scoring
- **LOW**: 1 point per violation
- **MEDIUM**: 5 points per violation
- **HIGH**: 10 points per violation
- **Compound Score**: Sum of all violation scores

## VTT Format Support
Parses standard WebVTT format:
```
WEBVTT

00:00:00.000 --> 00:00:05.000
Speaker Name: This is the spoken text

00:00:05.000 --> 00:00:10.000
Another Speaker: More dialogue here
```

## Error Handling
- **S3 Access Errors**: Validates file existence before processing
- **Parse Errors**: Gracefully handles malformed VTT blocks
- **DynamoDB Updates**: Updates job status on both success and failure
- **SQS Retry**: Failed messages return to queue for retry
- **Comprehensive Logging**: Detailed CloudWatch logs for debugging

## Performance Metrics
Based on the implementation:
- **Keyword Loading**: ~1-2 seconds for thousands of keywords
- **Transcript Parsing**: ~100-500 utterances/second
- **Pattern Matching**: ~1000+ utterances/second
- **Total Processing**: Typically < 30 seconds for hour-long transcripts

## Integration Flow
1. Receives job from entry-point via SQS
2. Downloads transcript and keywords from S3
3. Performs rules-based moderation
4. Uploads results to S3: `s3://OUTPUT_BUCKET/moderation-results/{job_id}/rules_result.json`
5. Updates DynamoDB with result location
6. Forwards job to LLM queue for advanced analysis

## AWS Permissions Required
- **S3**:
  - `s3:GetObject` on input buckets (transcripts, keywords)
  - `s3:PutObject` on output bucket
- **DynamoDB**: `dynamodb:UpdateItem` on job tracking table
- **SQS**:
  - `sqs:ReceiveMessage`, `sqs:DeleteMessage` on rules queue
  - `sqs:SendMessage` on LLM queue

## Monitoring and Alerts
Key metrics to monitor:
- **Processing Time**: Track via CloudWatch logs timestamps
- **Violation Rates**: Monitor compound scores and violation counts
- **Error Rate**: Track Lambda errors and DLQ messages
- **Queue Depth**: Monitor SQS queue backlog
- **Memory Usage**: Ensure sufficient Lambda memory for large transcripts

## Dependencies
- **pyahocorasick**: High-performance pattern matching library
- **boto3**: AWS SDK for Python
- **Built-in libraries**: json, csv, re, tempfile, dataclasses

## Usage Example
The function is triggered automatically via SQS, but can be tested with:
```python
# Test event
{
  "Records": [
    {
      "body": "{\"job_id\": \"test-123\", \"transcript_s3_url\": \"s3://my-bucket/transcript.vtt\"}"
    }
  ]
}
```

## Optimization Tips
1. **Keywords Management**: Keep keyword list focused and well-categorized
2. **Memory Allocation**: Allocate 512MB-1GB Lambda memory for optimal performance
3. **Timeout Settings**: Set Lambda timeout to 5-10 minutes for large transcripts
4. **Batch Size**: Configure SQS batch size of 1 for reliable processing

## Security Considerations
- All S3 operations use IAM roles (no hardcoded credentials)
- Temporary files are automatically cleaned up
- No sensitive data logged to CloudWatch
- Results stored with job-specific paths for access control