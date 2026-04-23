# app/core/storage_client.py
"""
Railway Object Storage client.
All presigned URLs expire in 23 hours.
"""

import logging

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from app.core.config import settings

logger = logging.getLogger(__name__)

PRESIGNED_URL_EXPIRY = 82_800  # 23 hours in seconds

_s3_client = None


def get_s3():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client(
            "s3",
            endpoint_url=settings.RAILWAY_ENDPOINT_URL,
            aws_access_key_id=settings.RAILWAY_ACCESS_KEY_ID,
            aws_secret_access_key=settings.RAILWAY_SECRET_ACCESS_KEY,
            region_name=settings.RAILWAY_REGION,
            config=Config(signature_version="s3v4"),
        )
    return _s3_client


def storage_upload(path: str, content: bytes, content_type: str) -> str:
    """Upload bytes to the Railway bucket. Returns the object key."""
    get_s3().put_object(
        Bucket=settings.RAILWAY_BUCKET_NAME,
        Key=path,
        Body=content,
        ContentType=content_type,
    )
    return path


def storage_delete(path: str) -> None:
    """Delete an object from the Railway bucket. Silent on missing keys."""
    if not path:
        return
    try:
        get_s3().delete_object(Bucket=settings.RAILWAY_BUCKET_NAME, Key=path)
    except ClientError as exc:
        logger.warning("storage_delete failed for '%s': %s", path, exc)


def storage_presigned_url(path: str) -> str:
    """Generate a presigned GET URL valid for 23 hours."""
    return get_s3().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.RAILWAY_BUCKET_NAME, "Key": path},
        ExpiresIn=PRESIGNED_URL_EXPIRY,
    )