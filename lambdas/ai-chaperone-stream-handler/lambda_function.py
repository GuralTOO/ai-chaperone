import json
import boto3
import urllib3
import time
import os
from typing import Optional, Dict, Any
from urllib.parse import urlparse


s3 = boto3.client('s3')
dynamodb = boto3.client('dynamodb')
http = urllib3.PoolManager(timeout=urllib3.Timeout(connect=5.0, read=10.0))
table_name = os.environ['DYNAMO_TABLE_NAME']

SEVERITY_LEVELS = {
    'SAFE': 0,
    'LOW': 1,
    'MEDIUM': 2,
    'HIGH': 3
}

def get_severity_level_name(level_value: int) -> str:
    """Convert severity level value back to name"""
    for name, value in SEVERITY_LEVELS.items():
        if value == level_value:
            return name
    return 'SAFE'

def parse_s3_url(s3_url: str) -> tuple:
    """Parse S3 URL to extract bucket and key"""
    if not s3_url or not s3_url.startswith('s3://'):
        return None, None

    path = s3_url[5:]  # Remove 's3://'
    parts = path.split('/', 1)
    if len(parts) != 2:
        return None, None

    return parts[0], parts[1]

def fetch_s3_file(s3_url: str) -> Optional[Dict[str, Any]]:
    """Fetch and parse JSON file from S3"""
    try:
        bucket, key = parse_s3_url(s3_url)
        if not bucket or not key:
            print(f"Invalid S3 URL: {s3_url}")
            return None

        response = s3.get_object(Bucket=bucket, Key=key)
        content = response['Body'].read().decode('utf-8')

        # Parse JSON with error handling
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            print(f"Invalid JSON in file {s3_url}: {str(e)}")
            return None

    except Exception as e:
        print(f"Error fetching {s3_url}: {str(e)}")
        return None

def get_highest_severity(files_data: list) -> str:
    """Calculate the highest severity level from multiple files"""
    max_severity = 0  # Start with SAFE

    for file_data in files_data:
        if not file_data:
            continue

        # Get the highest_severity_level field from the file
        severity_str = file_data.get('highest_severity_level')
        if not severity_str:
            print("Warning: missing highest_severity_level in file, defaulting to SAFE")
            continue

        # Convert to numeric value for comparison
        severity_value = SEVERITY_LEVELS.get(severity_str.upper(), -1)
        if severity_value == -1:
            print(f"Warning: unknown severity level '{severity_str}', ignoring")
            continue

        max_severity = max(max_severity, severity_value)

    return get_severity_level_name(max_severity)

def is_valid_url(url: str) -> bool:
    """Validate if URL is valid HTTP/HTTPS"""
    try:
        result = urlparse(url)
        return result.scheme in ['http', 'https'] and result.netloc != ''
    except Exception:
        return False

def call_webhook_with_retry(webhook_url: str, payload: dict, max_retries: int = 3) -> bool:
    """Call webhook with retry logic"""
    for attempt in range(max_retries):
        try:
            print(f"Calling webhook (attempt {attempt + 1}/{max_retries})")
            response = http.request(
                'POST',
                webhook_url,
                body=json.dumps(payload).encode('utf-8'),
                headers={'Content-Type': 'application/json'},
                retries=False  # Handle retries ourselves
            )

            if response.status >= 200 and response.status < 300:
                print(f"Successfully called webhook, status: {response.status}")
                return True
            else:
                print(f"Webhook call failed, status: {response.status}, body: {response.data}")

        except urllib3.exceptions.TimeoutError:
            print(f"Webhook call timed out (attempt {attempt + 1}/{max_retries})")
        except Exception as e:
            print(f"Error calling webhook (attempt {attempt + 1}/{max_retries}): {str(e)}")

        # Wait before retry (except for last attempt)
        if attempt < max_retries - 1:
            time.sleep(2 ** attempt)  # Exponential backoff: 1s, 2s, 4s

    return False

def update_combined_flag(job_id: str) -> bool:
    """Update the combined flag in DynamoDB"""
    try:
        dynamodb.update_item(
            TableName=table_name,
            Key={'job_id': {'S': job_id}},
            UpdateExpression='SET combined = :val, updated_at = :timestamp, #st = :st',
            ExpressionAttributeNames={
                '#st': 'status'
            },
            ExpressionAttributeValues={
                ':val': {'BOOL': True},
                ':st': {'S': 'COMPLETE'},
                ':timestamp': {'S': time.strftime('%Y-%m-%dT%H:%M:%S.%fZ')}
            }
        )
        print(f"Successfully updated combined flag for job {job_id}")
        return True
    except Exception as e:
        print(f"Error updating combined flag for job {job_id}: {str(e)}")
        return False

def lambda_handler(event, context):
    print(f"Processing {len(event['Records'])} stream records")

    for record in event['Records']:
        # Only process MODIFY events
        if record['eventName'] != 'MODIFY':
            print(f"Skipping {record['eventName']} event")
            continue

        old_image = record['dynamodb'].get('OldImage', {})
        new_image = record['dynamodb'].get('NewImage', {})

        # Check for required job_id field
        if 'job_id' not in new_image or 'S' not in new_image['job_id']:
            print("Error: Missing job_id in DynamoDB record, skipping")
            continue

        job_id = new_image['job_id']['S']

        old_transcript = old_image.get('transcript_complete', {}).get('BOOL', False)
        old_video = old_image.get('video_complete', {}).get('BOOL', False)

        new_transcript = new_image.get('transcript_complete', {}).get('BOOL', False)
        new_video = new_image.get('video_complete', {}).get('BOOL', False)
        combined = new_image.get('combined', {}).get('BOOL', False)

        # Check if this update just completed both branches
        was_incomplete = not (old_transcript and old_video)
        is_complete = new_transcript and new_video

        # print all of the variables in this row
        print(f"Processing job {job_id}, combined {combined}, webhook {new_image.get('webhook_url', {}).get('S', '')}, table_name {table_name}")


        if was_incomplete and is_complete and not combined:
            print(f"Job {job_id} ready for combination, processing...")

            # Check if webhook_url exists and is not empty
            webhook_url = new_image.get('webhook_url', {}).get('S', '')

            # If no webhook URL, just mark as combined and skip processing
            if not webhook_url:
                print(f"Job {job_id} has no webhook_url, marking as combined")
                if table_name:
                    update_combined_flag(job_id)
                continue

            # Validate webhook URL
            if not is_valid_url(webhook_url):
                print(f"Job {job_id} has invalid webhook_url: {webhook_url}, marking as combined")
                if table_name:
                    update_combined_flag(job_id)
                continue

            # Get S3 URLs from DynamoDB record
            rules_result_url = new_image.get('transcript_rules_result_s3_url', {}).get('S', '')
            llm_safety_result_url = new_image.get('transcript_llm_safety_result_s3_url', {}).get('S', '')
            llm_summary_result_url = new_image.get('transcript_llm_summary_result_s3_url', {}).get('S', '')
            image_llm_safety_result_url = new_image.get('video_llm_result_s3_url', {}).get('S', '')

            # Fetch files from S3
            print(f"Fetching safety analysis files for job {job_id}")
            rules_data = fetch_s3_file(rules_result_url) if rules_result_url else None
            llm_safety_data = fetch_s3_file(llm_safety_result_url) if llm_safety_result_url else None
            llm_summary_data = fetch_s3_file(llm_summary_result_url) if llm_summary_result_url else None
            image_llm_safety_data = fetch_s3_file(image_llm_safety_result_url) if image_llm_safety_result_url else None

            # Calculate highest severity levels
            # Transcript severity: highest from rules_result and llm_safety_result
            transcript_files = [rules_data, llm_safety_data]
            transcript_highest_severity = get_highest_severity(transcript_files)

            # Video severity: from image_llm_safety_result
            video_files = [image_llm_safety_data]
            video_highest_severity = get_highest_severity(video_files)

            # Build webhook payload
            webhook_payload = {
                'job_id': job_id,
                'transcript_highest_severity_level': transcript_highest_severity,
                'video_highest_severity_level': video_highest_severity,
                'rules_result_url': rules_result_url,
                'llm_safety_result_url': llm_safety_result_url,
                'llm_summary_result_url': llm_summary_result_url,
                'image_llm_safety_result_url': image_llm_safety_result_url
            }

            # Call webhook with retry logic
            webhook_success = call_webhook_with_retry(webhook_url, webhook_payload)

            # Update combined flag only if webhook succeeded
            if webhook_success:
                print(f"Webhook successful for job {job_id}, marking as combined")
                if table_name:
                    update_combined_flag(job_id)
            else:
                print(f"Webhook failed for job {job_id} after retries, NOT marking as combined")

    return {'statusCode': 200}
