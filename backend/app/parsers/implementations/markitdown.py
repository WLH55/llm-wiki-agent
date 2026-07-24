"""MarkItDown 高级解析器适配器。"""

import logging
from io import BytesIO
from typing import Any

from app.parsers.core.base import BaseParser
from app.parsers.core.document import Document

logger = logging.getLogger(__name__)


def _load_markitdown_class():
    """惰性导入 MarkItDown，避免默认安装缺高级依赖时导入失败。"""

    from markitdown import MarkItDown

    return MarkItDown


def markitdown_available() -> tuple[bool, str]:
    """检查 MarkItDown 是否可用。"""

    try:
        _load_markitdown_class()
    except ImportError as exc:
        return False, f"markitdown 未安装: {exc}"
    return True, ""


def _create_markitdown():
    """创建 MarkItDown 实例，单独封装便于测试替换。"""

    markitdown_cls = _load_markitdown_class()
    return markitdown_cls()


def _normalize_file_extension(file_type: str | None, file_name: str) -> str | None:
    """把 file_type/file_name 统一成 MarkItDown 需要的 .ext 形式。"""

    raw = (file_type or "").strip()
    if not raw and "." in file_name:
        raw = file_name.rsplit(".", 1)[-1]
    raw = raw.lstrip(".").lower()
    return f".{raw}" if raw else None


def _convert_with_data_uris(
    engine: Any,
    content: bytes,
    file_extension: str | None,
):
    """优先保留 data URI；旧版库不支持该参数时降级转换。"""

    kwargs: dict[str, Any] = {"file_extension": file_extension, "keep_data_uris": True}
    try:
        return engine.convert(BytesIO(content), **kwargs)
    except TypeError as exc:
        if "keep_data_uris" not in str(exc):
            raise
        kwargs.pop("keep_data_uris")
        return engine.convert(BytesIO(content), **kwargs)


def _extract_markdown_text(result: Any) -> str:
    """兼容不同版本 MarkItDown 的返回字段。"""

    if result is None:
        return ""
    if isinstance(result, str):
        return result
    for attr in ("text_content", "markdown", "content"):
        value = getattr(result, attr, None)
        if isinstance(value, str):
            return value
    return ""


class MarkitdownParser(BaseParser):
    """使用微软 MarkItDown 将文档 bytes 转成 Markdown。"""

    def parse_into_text(self, content: bytes) -> Document:
        """执行 MarkItDown 转换，失败时返回带 error metadata 的空 Document。"""

        metadata = {"parser_engine": "markitdown"}
        file_extension = _normalize_file_extension(self.file_type, self.file_name)
        try:
            engine = _create_markitdown()
            result = _convert_with_data_uris(engine, content, file_extension)
            text = _extract_markdown_text(result)
        except ImportError as exc:
            logger.warning("MarkItDown 依赖不可用：%s", exc)
            return Document(
                content="",
                metadata={**metadata, "error": f"dependency_unavailable: {exc}"},
            )
        except Exception as exc:
            logger.error("MarkItDown 转换失败：%s", exc)
            return Document(
                content="",
                metadata={**metadata, "error": f"convert_failed: {exc}"},
            )
        if not text.strip():
            return Document(
                content="",
                metadata={**metadata, "error": "empty_result"},
            )
        return Document(content=text, metadata=metadata)
