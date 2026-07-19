"""按文件名与可选 engine 派发 parser 并提取文本。"""
import logging
import os

from app.parsers import registry as parser_registry
from app.parsers.text_parser import TextParser

logger = logging.getLogger(__name__)


def parse_to_text(
    filename: str,
    raw_bytes: bytes,
    engine: str | None = None,
) -> str:
    """用 Registry 派发 parser 并提取文本。

    - engine 为空：按 builtin + file_type 查询（兼容旧调用）
    - engine 指定：按 (engine, file_type) 查询，未命中时 Registry 回退 builtin
    - 未注册的 file_type：兜底走 TextParser
    """
    file_type = os.path.splitext(filename or "")[1].lstrip(".").lower()
    try:
        if engine:
            parser_cls = parser_registry.get_parser_class(engine, file_type)
        else:
            parser_cls = parser_registry.get_parser_class(file_type)
    except KeyError:
        logger.warning("未知扩展名 %r，按文本处理: %s", file_type, filename)
        parser_cls = TextParser
    document = parser_cls(file_name=filename).parse(raw_bytes)
    return document.content
