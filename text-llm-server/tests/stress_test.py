import boto3
import json

S3_BUCKET = "recordings-prod-us-east-2"
S3_PREFIX = "zoom/"
LAMBDA_FUNCTION_NAME = "ai-chaperone-entry-point"
REGION = 'us-east-1'
LAMBDA_REGION = 'us-east-2'
N = 20

s3 = boto3.client("s3", region_name=REGION)
lambda_client = boto3.client("lambda", region_name=LAMBDA_REGION)

def list_folders(bucket, prefix):
    folders = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix, Delimiter="/"):
        if "CommonPrefixes" in page:
            folders.extend([p["Prefix"] for p in page["CommonPrefixes"]])
    return folders

def find_files(bucket, folder):
    vtt = mp4 = None
    paginator = s3.get_paginator('list_objects_v2')
    
    for page in paginator.paginate(Bucket=bucket, Prefix=folder):
        for obj in page.get('Contents', []):
            key = obj['Key']
            if key.endswith('.VTT') and not vtt:
                vtt = f's3://{bucket}/{key}'
            if key.endswith('.MP4') and 'audio_only' not in key and not mp4:
                mp4 = f's3://{bucket}/{key}'
            if vtt and mp4:
                return vtt, mp4
    return vtt, mp4

def invoke_lambda(vtt_uri, mp4_uri):
    payload = {"transcript_s3_url": vtt_uri, "video_s3_url": mp4_uri, "webhook_url": ""}
    lambda_client.invoke(
        FunctionName=LAMBDA_FUNCTION_NAME,
        InvocationType="Event",
        Payload=json.dumps(payload)
    )
    print(f"Invoked: {payload}")

folders = list_folders(S3_BUCKET, S3_PREFIX)
print(f"Found {len(folders)} folders")

valid = []
for folder in folders:
    vtt, mp4 = find_files(S3_BUCKET, folder)
    if vtt and mp4:
        valid.append({"vtt": vtt, "mp4": mp4})
        if len(valid) >= N:
            break

print(f"Found {len(valid)} valid folders")

for i , item in enumerate(valid):
    if i > N:
        break
    invoke_lambda(item["vtt"], item["mp4"])