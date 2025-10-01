import json
import uuid
import boto3
import os
from datetime import datetime
from urllib.parse import urlparse

TABLE_NAME = os.environ.get('DYNAMO_TABLE_NAME')
RULES_QUEUE_URL = os.environ.get('RULES_QUEUE_URL')
IMAGE_QUEUE_URL = os.environ.get('IMAGE_QUEUE_URL')

dynamodb = boto3.resource('dynamodb')
sqs = boto3.client('sqs')
s3 = boto3.client('s3')
table = dynamodb.Table(TABLE_NAME)

def parse_s3_url(s3_url):
    """Parse S3 URL and return bucket and key"""
    if not s3_url.startswith('s3://'):
        raise ValueError(f"Invalid S3 URL format: {s3_url}")
    
    parsed = urlparse(s3_url)
    bucket = parsed.netloc
    key = parsed.path.lstrip('/')
    
    if not bucket or not key:
        raise ValueError(f"Invalid S3 URL: {s3_url}")
    
    return bucket, key

def validate_s3_files(transcript_url, video_url):
    """
    Validate that S3 files exist and are accessible
    Returns: (success, error_message)
    """
    try:
        transcript_bucket, transcript_key = parse_s3_url(transcript_url)
        s3.head_object(Bucket=transcript_bucket, Key=transcript_key)
        
        video_bucket, video_key = parse_s3_url(video_url)
        video_response = s3.head_object(Bucket=video_bucket, Key=video_key)

        return True, None
        
    except s3.exceptions.NoSuchKey as e:
        return False, f"File not found: {str(e)}"
    except Exception as e:
        return False, f"S3 validation error: {str(e)}"

def lambda_handler(event, context):
    """
    Expected input format:
    {
        "transcript_s3_url": "s3://bucket/path/to/transcript.txt",
        "video_s3_url": "s3://bucket/path/to/video.mp4",
        "webhook_url": "",
    }
    """
    
    try:
        if isinstance(event.get('body'), str):
            body = json.loads(event['body'])
        else:
            body = event
        
        # Validate fields
        if not body.get('transcript_s3_url') or not body.get('video_s3_url'):
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Missing required fields: transcript_s3_url, video_s3_url'})
            }

        # Validate S3 files exist
        valid, error_msg = validate_s3_files(
            body['transcript_s3_url'], 
            body['video_s3_url']
        )
        
        if not valid:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': f'S3 validation failed: {error_msg}'})
            }
        
        # Generate job ID
        job_id = str(uuid.uuid4())
        timestamp = int(datetime.now().timestamp())
        
        # Create job entry in DynamoDB
        job_item = {
            'job_id': job_id,
            'status': 'PROCESSING',
            'transcript_complete': False,
            'video_complete': False,
            'combined': False,
            'transcript_s3_url': body['transcript_s3_url'],
            'video_s3_url': body['video_s3_url'],
            'webhook_url': body.get('webhook_url', ''),
            'transcript_rules_result_s3_url': '',
            'transcript_llm_summary_result_s3_url': '',
            'transcript_llm_safety_result_s3_url': '',
            'video_llm_result_s3_url': '',
            'metadata': body.get('metadata', {}),
            'created_at': timestamp,
            'updated_at': timestamp
        }
        
        table.put_item(Item=job_item)
        
        # Queue message for rules transcript processing
        rules_message = {
            'job_id': job_id,
            'transcript_s3_url': body['transcript_s3_url']
        }
        
        sqs.send_message(
            QueueUrl=RULES_QUEUE_URL,
            MessageBody=json.dumps(rules_message)
        )
        
        # Queue message for image processing of the video (sampling + llm image processing)
        image_message = {
            'job_id': job_id,
            'video_s3_url': body['video_s3_url']
        }
        
        sqs.send_message(
            QueueUrl=IMAGE_QUEUE_URL,
            MessageBody=json.dumps(image_message)
        )
        
        # Return success
        return {
            'statusCode': 200,
            'body': json.dumps({
                'job_id': job_id,
                'status': 'processing',
                'message': 'Job queued successfully'
            })
        }
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
