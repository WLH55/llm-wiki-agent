"""按文件名与可选 engine 派发 parser，并返回完整生产结果。"""

import base64
import binascii
import logging
import os

from app.config import settings
from app.parsers import registry as parser_registry
from app.parsers.registry import BUILTIN_ENGINE
from app.parsers.result import (
    ParseDispatchError,
    ParseErrorCode,
    ParseLimits,
    ParseResult,
    map_legacy_error,
)

logger = logging.getLogger(__name__)


def _default_limits() -> ParseLimits:
    return ParseLimits(
        max_file_bytes=settings.PARSER_MAX_FILE_BYTES,
        max_output_chars=settings.PARSER_MAX_OUTPUT_CHARS,
        max_total_image_bytes=settings.PARSER_MAX_TOTAL_IMAGE_BYTES,
    )


def _failure(
    engine: str,
    error_code: ParseErrorCode,
    message: str,
    metadata: dict | None = None,
) -> ParseResult:
    result_metadata = dict(metadata or {})
    result_metadata.setdefault("error", message)
    return ParseResult(
        engine=engine,
        error_code=error_code,
        metadata=result_metadata,
    )


def parse_document(
    filename: str,
    raw_bytes: bytes,
    engine: str = BUILTIN_ENGINE,
    limits: ParseLimits | None = None,
) -> ParseResult:
    """严格派发 parser，并把所有失败收敛为 ParseResult。"""

    selected_engine = (engine or BUILTIN_ENGINE).strip().lower()
    active_limits = limits or _default_limits()
    file_type = os.path.splitext(filename or "")[1].lstrip(".").lower()
    if len(raw_bytes) > active_limits.max_file_bytes:
        return _failure(selected_engine, ParseErrorCode.TOO_LARGE, "file_too_large")
    engine_status = parser_registry.get_engine_status(selected_engine)
    if engine_status is None or not engine_status["available"]:
        reason = (
            "unknown_engine" if engine_status is None else str(engine_status["unavailable_reason"])
        )
        return _failure(selected_engine, ParseErrorCode.ENGINE_UNAVAILABLE, reason)
    try:
        parser_cls = parser_registry.get_parser_class(
            selected_engine,
            file_type,
            fallback_to_builtin=False,
        )
    except KeyError:
        error_code = (
            ParseErrorCode.UNSUPPORTED_TYPE
            if selected_engine == BUILTIN_ENGINE
            else ParseErrorCode.ENGINE_UNAVAILABLE
        )
        return _failure(
            selected_engine,
            error_code,
            f"unsupported_file_type: {file_type or 'unknown'}",
        )
    try:
        document = parser_cls(file_name=filename).parse(raw_bytes)
    except Exception as exc:
        logger.exception("解析器异常: file=%s engine=%s", filename, selected_engine)
        return _failure(selected_engine, ParseErrorCode.PARSE_FAILED, str(exc))
    metadata = dict(document.metadata)
    if metadata.get("error"):
        return ParseResult(
            content=document.content,
            images=document.images,
            metadata=metadata,
            engine=selected_engine,
            error_code=map_legacy_error(metadata["error"]),
        )
    if not document.content.strip():
        metadata.setdefault("error", "empty_content")
        return ParseResult(
            images=document.images,
            metadata=metadata,
            engine=selected_engine,
            error_code=ParseErrorCode.EMPTY_CONTENT,
        )
    if len(document.content) > active_limits.max_output_chars:
        return _failure(
            selected_engine,
            ParseErrorCode.TOO_LARGE,
            "output_too_large",
            metadata,
        )
    total_image_bytes = 0
    try:
        for encoded in document.images.values():
            total_image_bytes += len(base64.b64decode(encoded, validate=True))
            if total_image_bytes > active_limits.max_total_image_bytes:
                return _failure(
                    selected_engine,
                    ParseErrorCode.TOO_LARGE,
                    "images_too_large",
                    metadata,
                )
    except (ValueError, binascii.Error):
        return _failure(
            selected_engine,
            ParseErrorCode.PARSE_FAILED,
            "invalid_image_base64",
            metadata,
        )
    warnings = list(metadata.get("warnings", []))
    if metadata.get("empty_page_count") and not metadata.get("is_scanned"):
        warnings.append("partial_empty_pages")
    return ParseResult(
        content=document.content,
        images=document.images,
        metadata=metadata,
        engine=selected_engine,
        warnings=list(dict.fromkeys(warnings)),
    )


def parse_to_text(
    filename: str,
    raw_bytes: bytes,
    engine: str | None = None,
) -> str:
    """兼容旧文本调用；失败时抛出带稳定错误码的异常。"""

    result = parse_document(filename, raw_bytes, engine or BUILTIN_ENGINE)
    if result.error_code is not None:
        raise ParseDispatchError(
            result.error_code,
            str(result.metadata.get("error", result.error_code.value)),
        )
    return result.content
