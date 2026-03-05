"""
MinIO client using boto3 S3-compatible API (replaces Supabase Storage).
Usage: from app.core.minio_client import minio_upload, minio_delete, minio_get_url
"""
import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

_s3_client = None


def get_s3():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client(
            "s3",
            endpoint_url=settings.MINIO_ENDPOINT,
            aws_access_key_id=settings.MINIO_ACCESS_KEY,
            aws_secret_access_key=settings.MINIO_SECRET_KEY,
            config=Config(signature_version="s3v4"),
            region_name="us-east-1",  # MinIO ignores this but boto3 requires it
        )
    return _s3_client


def minio_upload(bucket: str, path: str, content: bytes, content_type: str) -> str:
    """
    Upload bytes to MinIO. Returns the object path (not a URL).
    Use minio_get_url() to get a presigned URL afterwards.
    """
    s3 = get_s3()
    s3.put_object(
        Bucket=bucket,
        Key=path,
        Body=content,
        ContentType=content_type,
    )
    return path


def minio_delete(bucket: str, path: str) -> None:
    """Delete a single object from MinIO. Does not raise on missing keys."""
    try:
        s3 = get_s3()
        s3.delete_object(Bucket=bucket, Key=path)
    except ClientError as e:
        logger.warning(f"MinIO delete failed for {bucket}/{path}: {e}")


def minio_get_url(bucket: str, path: str, expires_in: int = 86400 * 365) -> str:
    """
    Generate a presigned GET URL for a MinIO object.
    Default expiry: 1 year (in seconds).
    """
    s3 = get_s3()
    url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": path},
        ExpiresIn=expires_in,
    )
    return url


def minio_get_public_url(bucket: str, path: str) -> str:
    """
    Return a direct public URL (use this if your MinIO bucket is public).
    Format: <MINIO_ENDPOINT>/<bucket>/<path>
    """
    endpoint = settings.MINIO_ENDPOINT.rstrip("/")
    return f"{settings.MINIO_PUBLIC_URL.rstrip('/')}/{bucket}/{path}"