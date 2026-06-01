import os
import boto3

S3_BUCKET = os.environ["S3_BUCKET"]

s3 = boto3.client("s3")


def upload_file(file_bytes: bytes, s3_key: str, content_type: str = "application/pdf") -> str:
    s3.put_object(
        Bucket=S3_BUCKET,
        Key=s3_key,
        Body=file_bytes,
        ContentType=content_type,
    )
    return s3_key


def generate_presigned_url(s3_key: str, expires_in: int = 3600) -> str:
    return s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": S3_BUCKET, "Key": s3_key},
        ExpiresIn=expires_in,
    )
