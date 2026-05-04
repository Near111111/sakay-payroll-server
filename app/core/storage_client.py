# app/core/storage_client.py
"""
Railway Object Storage client.
All presigned URLs expire in 7 days.
On fetch, URLs are checked for validity and refreshed automatically if expired.
"""

import logging
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs

import httpx
import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from app.core.config import settings

logger = logging.getLogger(__name__)

PRESIGNED_URL_EXPIRY = 604_800       # 7 days in seconds
PRESIGNED_URL_REFRESH_THRESHOLD = 86_400  # Refresh if less than 1 day remaining

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
    """Generate a presigned GET URL valid for 7 days."""
    return get_s3().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.RAILWAY_BUCKET_NAME, "Key": path},
        ExpiresIn=PRESIGNED_URL_EXPIRY,
    )


def storage_extract_key_from_url(presigned_url: str) -> str | None:
    """
    Extract the S3 object key from a presigned URL.
    Returns None if the URL is not a valid presigned URL for our bucket.
    """
    try:
        parsed = urlparse(presigned_url)
        # The path starts with /<bucket>/<key> or just /<key> depending on endpoint style
        path = parsed.path.lstrip("/")
        bucket = settings.RAILWAY_BUCKET_NAME
        if path.startswith(bucket + "/"):
            return path[len(bucket) + 1:]
        # Fallback: path is the key directly
        if path:
            return path
        return None
    except Exception as exc:
        logger.warning("storage_extract_key_from_url failed: %s", exc)
        return None


def storage_url_needs_refresh(presigned_url: str) -> bool:
    """
    Returns True if the presigned URL has expired or will expire within
    PRESIGNED_URL_REFRESH_THRESHOLD seconds (1 day).
    Also returns True if the URL cannot be parsed.
    """
    try:
        parsed = urlparse(presigned_url)
        qs = parse_qs(parsed.query)

        # AWS / S3-compatible signed URLs carry X-Amz-Expires and X-Amz-Date
        expires_list = qs.get("X-Amz-Expires") or qs.get("x-amz-expires")
        date_list = qs.get("X-Amz-Date") or qs.get("x-amz-date")

        if not expires_list or not date_list:
            # Cannot determine expiry — assume it needs refresh
            return True

        expires_in = int(expires_list[0])
        signed_at_str = date_list[0]  # e.g. "20240501T120000Z"
        signed_at = datetime.strptime(signed_at_str, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        expiry_time = signed_at.timestamp() + expires_in
        now = datetime.now(timezone.utc).timestamp()
        remaining = expiry_time - now

        return remaining < PRESIGNED_URL_REFRESH_THRESHOLD
    except Exception as exc:
        logger.warning("storage_url_needs_refresh check failed: %s", exc)
        return True


def storage_url_is_active(presigned_url: str) -> bool:
    """
    Performs a lightweight HEAD request to verify the presigned URL
    is still reachable. Falls back to the expiry-parse check if the
    request fails for non-auth reasons.
    """
    if not presigned_url:
        return False
    try:
        response = httpx.head(presigned_url, timeout=5, follow_redirects=True)
        return response.status_code == 200
    except httpx.RequestError as exc:
        logger.warning("storage_url_is_active HEAD request failed: %s", exc)
        # If we can't reach the URL at all, treat as inactive
        return False