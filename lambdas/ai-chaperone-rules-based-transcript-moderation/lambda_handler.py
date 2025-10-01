import json
import boto3
import os
import tempfile
import time
from datetime import datetime
from transcript_moderation_optimized import ModerationEngine, TranscriptParser

# Initialize AWS clients
s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")
sqs = boto3.client("sqs")

# Environment variables
BAD_KEYWORDS_PATH = os.environ.get("BAD_KEYWORDS_PATH")
DYNAMO_TABLE_NAME = os.environ.get("DYNAMO_TABLE_NAME")
OUTPUT_BUCKET = os.environ.get("OUTPUT_BUCKET")
RULES_QUEUE_URL = os.environ.get("RULES_QUEUE_URL")
TEXT_LLM_QUEUE_URL = os.environ.get("TEXT_LLM_QUEUE_URL")


def parse_s3_url(s3_url):
    if not s3_url.startswith("s3://"):
        raise ValueError(f"Invalid S3 URL format: {s3_url}")

    path = s3_url[5:]
    parts = path.split("/", 1)

    if len(parts) != 2:
        raise ValueError(f"Invalid S3 URL format: {s3_url}")

    return parts[0], parts[1]


def lambda_handler(event, context):
    """

    Expected SQS message structure:
    {
        "job_id": "c45eb5bd-1b13-4689-a770-3fcd83439264",
        "transcript_s3_url": "s3://recordings-dev-us-east-2/zoom/.../audio_transcript.VTT"
    }
    """

    if not BAD_KEYWORDS_PATH:
        raise ValueError("BAD_KEYWORDS_PATH environment variable must be set")
    if not OUTPUT_BUCKET:
        raise ValueError("OUTPUT_BUCKET environment variable must be set")

    if "Records" not in event or len(event["Records"]) == 0:
        raise ValueError("No SQS records found in event")

    record = event["Records"][0]

    try:
        # Parse SQS message body
        message_body = json.loads(record["body"])
        job_id = message_body.get("job_id")
        transcript_s3_url = message_body.get("transcript_s3_url")

        if not job_id or not transcript_s3_url:
            raise ValueError("Missing required fields: job_id or transcript_s3_url")

        print(f"Processing job_id: {job_id}")
        print(f"Transcript URL: {transcript_s3_url}")

        start_time = time.time()

        # Parse S3 URLs
        input_bucket, transcript_key = parse_s3_url(transcript_s3_url)
        keywords_bucket, keywords_key = parse_s3_url(BAD_KEYWORDS_PATH)


        with tempfile.TemporaryDirectory() as temp_dir:
            download_start = time.time()
            transcript_path = os.path.join(temp_dir, "transcript.vtt")
            print(f"Downloading transcript from {transcript_s3_url}")
            s3.download_file(input_bucket, transcript_key, transcript_path)
            print(
                f"Transcript downloaded in {time.time() - download_start:.2f} seconds"
            )

            keywords_start = time.time()
            keywords_path = os.path.join(temp_dir, "keywords.csv")
            print(f"Downloading keywords from {BAD_KEYWORDS_PATH}")
            s3.download_file(keywords_bucket, keywords_key, keywords_path)
            print(f"Keywords downloaded in {time.time() - keywords_start:.2f} seconds")

            engine_start = time.time()
            print("Loading keywords into moderation engine...")
            engine = ModerationEngine(keywords_path)
            print(f"Keywords loaded in {time.time() - engine_start:.2f} seconds")

            parse_start = time.time()
            print("Reading transcript file...")
            with open(transcript_path, "r", encoding="utf-8") as f:
                content = f.read()
            print(f"Transcript read in {time.time() - parse_start:.2f} seconds")

            parse_vtt_start = time.time()
            print("Parsing VTT content...")
            utterances = TranscriptParser.parse_vtt(content)
            print(
                f"Parsed {len(utterances)} utterances in {time.time() - parse_vtt_start:.2f} seconds"
            )

            violations = []
            moderation_start = time.time()
            print(f"Starting moderation of {len(utterances)} utterances...")
            processed_count = 0
            last_log_time = time.time()

            for i, utterance in enumerate(utterances):
                found_violations = engine.matcher.find_violations(utterance.text)
                for violation_data in found_violations:
                    violations.append(
                        {
                            "keyword": violation_data["keyword"],
                            "speaker": utterance.speaker,
                            "text": utterance.text,
                            "timestamp": utterance.start_time,
                            "categories": violation_data["categories"],
                            "severity": violation_data["severity"],
                        }
                    )

                processed_count += 1

                if time.time() - last_log_time > 10:
                    elapsed = time.time() - moderation_start
                    rate = processed_count / elapsed
                    remaining = (
                        (len(utterances) - processed_count) / rate if rate > 0 else 0
                    )
                    print(
                        f"Progress: {processed_count}/{len(utterances)} utterances processed "
                        f"({processed_count * 100 / len(utterances):.1f}%) - "
                        f"Rate: {rate:.1f} utterances/sec - "
                        f"Est. remaining: {remaining:.1f} seconds"
                    )
                    last_log_time = time.time()

            print(
                f"Moderation completed in {time.time() - moderation_start:.2f} seconds"
            )
            print(f"Found {len(violations)} total violations")

            # Calculate severity scores
            analysis_start = time.time()
            print("Analyzing violations and creating report...")
            severity_scores = {"LOW": 1, "MEDIUM": 5, "HIGH": 10}
            compound_score = sum(
                severity_scores.get(v["severity"], 1) for v in violations
            )

            # Find highest severity
            if violations:
                severity_order = ["HIGH", "MEDIUM", "LOW"]
                highest_severity = next(
                    (
                        sev
                        for sev in severity_order
                        if any(v["severity"] == sev for v in violations)
                    ),
                    "LOW",
                )
            else:
                highest_severity = None

            # Create category-based report
            category_report = {}
            for violation in violations:
                for category in violation["categories"]:
                    if category not in category_report:
                        category_report[category] = {
                            "count": 0,
                            "violations": [],
                            "speakers": set(),
                        }
                    category_report[category]["count"] += 1
                    category_report[category]["violations"].append(
                        {
                            "keyword": violation["keyword"],
                            "speaker": violation["speaker"],
                            "timestamp": violation["timestamp"],
                            "severity": violation["severity"],
                        }
                    )
                    category_report[category]["speakers"].add(violation["speaker"])

            for category in category_report:
                category_report[category]["speakers"] = list(
                    category_report[category]["speakers"]
                )

            # Prepare results
            results = {
                "job_id": job_id,
                "transcript_file": transcript_key,
                "transcript_s3_url": transcript_s3_url,
                "processed_at": datetime.utcnow().isoformat(),
                "total_utterances": len(utterances),
                "total_violations": len(violations),
                "compound_severity_score": compound_score,
                "highest_severity_level": highest_severity,
                "violations": violations,
                "speakers_with_violations": list(set(v["speaker"] for v in violations)),
                "category_report": category_report,
            }

            print(
                f"Report analysis completed in {time.time() - analysis_start:.2f} seconds"
            )

            # Generate output filename with job_id
            timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
            output_key = f"moderation-results/{job_id}/rules_result.json"

            # Upload results to S3
            upload_start = time.time()
            output_location = f"s3://{OUTPUT_BUCKET}/{output_key}"
            print(f"Uploading results to {output_location}")
            s3.put_object(
                Bucket=OUTPUT_BUCKET,
                Key=output_key,
                Body=json.dumps(results, indent=2, ensure_ascii=False),
                ContentType="application/json",
            )
            print(f"Upload completed in {time.time() - upload_start:.2f} seconds")

            # Update DynamoDB with completion status
            if DYNAMO_TABLE_NAME:
                table = dynamodb.Table(DYNAMO_TABLE_NAME)
                table.update_item(
                    Key={"job_id": job_id},
                    UpdateExpression="set transcript_rules_result_s3_url=:o, updated_at=:u",
                    ExpressionAttributeValues={
                        ":o": output_location,
                        ":u": datetime.utcnow().isoformat(),
                    },
                )

            # Send to TEXT_LLM_QUEUE
            if TEXT_LLM_QUEUE_URL:
                print(f"Sending violations to LLM queue for further processing...")
                sqs.send_message(
                    QueueUrl=TEXT_LLM_QUEUE_URL,
                    MessageBody=json.dumps(
                        {
                            "job_id": job_id,
                            "transcript_s3_url": transcript_s3_url,
                        }
                    ),
                )
                print("Message sent to LLM queue")

            # Log summary
            total_time = time.time() - start_time
            print(f"\nProcessing completed successfully:")
            print(f"  - Job ID: {job_id}")
            print(f"  - Total time: {total_time:.2f} seconds")
            print(f"  - Utterances: {len(utterances)}")
            print(f"  - Violations: {len(violations)}")
            print(f"  - Output: {output_location}")

            # Return success response
            return {
                "statusCode": 200,
                "body": json.dumps(
                    {
                        "message": "Moderation completed successfully",
                        "job_id": job_id,
                        "output_location": output_location,
                        "total_violations": len(violations),
                        "highest_severity": highest_severity,
                    }
                ),
            }

    except Exception as e:
        error_msg = f"Error processing job {job_id if 'job_id' in locals() else 'unknown'}: {str(e)}"
        print(error_msg)

        # Update DynamoDB with error status if possible
        if DYNAMO_TABLE_NAME and "job_id" in locals():
            try:
                table = dynamodb.Table(DYNAMO_TABLE_NAME)
                table.update_item(
                    Key={"job_id": job_id},
                    UpdateExpression="SET #status = :status, error_message = :error, failed_at = :failed, updated_at = :updated",
                    ExpressionAttributeNames={"#status": "status"},
                    ExpressionAttributeValues={
                        ":status": "FAILED",
                        ":error": str(e),
                        ":failed": datetime.utcnow().isoformat(),
                        ":updated": datetime.utcnow().isoformat(),
                    },

                )
            except Exception as db_error:
                print(f"Failed to update DynamoDB: {db_error}")

        # Re-raise the exception so Lambda knows processing failed
        # This will cause the message to be retried or sent to DLQ
        raise
