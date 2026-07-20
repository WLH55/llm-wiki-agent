"""
MinIO 服务：原始文件存取
"""

import io
import logging
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

_client: Any = None


def get_minio_client() -> Any:
    """获取 MinIO client（懒加载单例）"""
    global _client
    if _client is None:
        from minio import Minio

        _client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )
    return _client


def ensure_bucket(bucket: str | None = None) -> None:
    """确保 bucket 存在"""
    bucket = bucket or settings.MINIO_BUCKET
    client = get_minio_client()
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)
        logger.info(f"MinIO bucket 已创建: {bucket}")


def upload_bytes(
    key: str,
    data: bytes,
    content_type: str = "application/octet-stream",
    bucket: str | None = None,
) -> str:
    """上传字节流，返回 "{bucket}/{key}" 标识"""
    bucket = bucket or settings.MINIO_BUCKET
    ensure_bucket(bucket)
    client = get_minio_client()
    client.put_object(
        bucket_name=bucket,
        object_name=key,
        data=io.BytesIO(data),
        length=len(data),
        content_type=content_type,
    )
    return f"{bucket}/{key}"


def get_bytes(key: str, bucket: str | None = None) -> bytes:
    """下载字节流"""
    bucket = bucket or settings.MINIO_BUCKET
    client = get_minio_client()
    response = client.get_object(bucket, key)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()
