import boto3
from botocore.exceptions import ClientError
from app.config import settings


def _s3():
    # boto3 finds AWS credentials automatically:
    # - On EKS: uses the IRSA role attached to the pod's service account
    # - Locally: uses ~/.aws/credentials or environment variables
    # Never hardcode credentials here
    return boto3.client("s3", region_name=settings.AWS_REGION)


def upload_file(content: bytes, s3_key: str, content_type: str = "application/octet-stream") -> str:
    # Upload raw bytes to S3 under the given key (path)
    # Returns the s3_key so callers can store it in the database
    _s3().put_object(
        Bucket=settings.S3_BUCKET,
        Key=s3_key,
        Body=content,
        ContentType=content_type,
    )
    return s3_key


def download_file(s3_key: str) -> bytes:
    # Download a file from S3 and return its raw bytes
    response = _s3().get_object(Bucket=settings.S3_BUCKET, Key=s3_key)
    return response["Body"].read()


def generate_presigned_url(s3_key: str, expires_in: int = 3600) -> str:
    # Generate a temporary URL that anyone can use to download the file
    # expires_in = seconds until the link expires (default: 1 hour)
    # This avoids exposing the S3 bucket publicly — the URL is the access token
    return _s3().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.S3_BUCKET, "Key": s3_key},
        ExpiresIn=expires_in,
    )


def delete_file(s3_key: str) -> None:
    # Delete a file from S3 — used when cleaning up drafts or test uploads
    try:
        _s3().delete_object(Bucket=settings.S3_BUCKET, Key=s3_key)
    except ClientError:
        pass  # if the file doesn't exist, that's fine — goal is it's gone


def file_exists(s3_key: str) -> bool:
    # Check if a file exists in S3 without downloading it
    try:
        _s3().head_object(Bucket=settings.S3_BUCKET, Key=s3_key)
        return True
    except ClientError:
        return False
