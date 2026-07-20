"""解析派生图片的安全持久化与正文引用替换。"""

import base64
import binascii
import hashlib
import mimetypes
import re
from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import Any
from uuid import UUID

from app.config import settings
from app.parsers.markdown_parser import MarkdownImageUtil
from app.parsers.result import ParseErrorCode
from app.services.minio_service import upload_bytes

_UNSAFE_NAME = re.compile(r"[^\w.-]+")


class ParserAssetError(RuntimeError):
    """图片解码或持久化失败。"""

    def __init__(self, error_code: ParseErrorCode, message: str) -> None:
        self.error_code = error_code
        super().__init__(message)


def _safe_basename(source_path: str) -> str:
    normalized = source_path.replace("\\", "/")
    basename = PurePosixPath(normalized).name
    safe_name = _UNSAFE_NAME.sub("_", basename).strip("._")
    return safe_name or "image.bin"


def persist_parser_images(
    kb_id: int,
    doc_id: UUID,
    content: str,
    images: Mapping[str, str],
    max_total_bytes: int,
) -> tuple[str, list[dict[str, Any]]]:
    """上传 parser 图片并把 Markdown 源路径替换为稳定 MinIO URI。"""

    replacements: dict[str, str] = {}
    persisted: list[dict[str, Any]] = []
    decoded_images: list[tuple[str, bytes]] = []
    total_bytes = 0
    for source_path, encoded in images.items():
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ParserAssetError(
                ParseErrorCode.PARSE_FAILED,
                f"invalid_image_base64: {source_path}",
            ) from exc
        total_bytes += len(raw)
        if total_bytes > max_total_bytes:
            raise ParserAssetError(ParseErrorCode.TOO_LARGE, "images_too_large")
        decoded_images.append((source_path, raw))
    for source_path, raw in decoded_images:
        safe_name = _safe_basename(source_path)
        digest = hashlib.sha256(raw).hexdigest()[:12]
        object_key = f"{kb_id}/{doc_id}/images/{digest}-{safe_name}"
        content_type = mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
        try:
            upload_bytes(object_key, raw, content_type)
        except Exception as exc:
            raise ParserAssetError(
                ParseErrorCode.PARSE_FAILED,
                f"image_upload_failed: {source_path}",
            ) from exc
        uri = f"minio://{settings.MINIO_BUCKET}/{object_key}"
        replacements[source_path] = uri
        persisted.append(
            {
                "source_path": source_path,
                "object_key": object_key,
                "uri": uri,
                "content_type": content_type,
                "size_bytes": len(raw),
            }
        )
    rewritten = MarkdownImageUtil().replace_path(content, replacements)
    return rewritten, persisted
