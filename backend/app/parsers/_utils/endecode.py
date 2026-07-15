"""编码处理 utils。

只处理文本 bytes ↔ str 转换。图片相关（base64 编解码）留到 Step 17 MarkdownImageBase64 时再加。

设计：
- decode_bytes 用 fallback chain（utf-8 → 中文编码 → latin-1 兜底），永不抛异常
- encode_bytes 直接 UTF-8（产出 bytes 的场景几乎都是给网络/磁盘，UTF-8 是标准）
"""
import logging
from typing import List

logger = logging.getLogger(__name__)


def encode_bytes(content: str) -> bytes:
    """str → bytes（UTF-8）。PipelineParser 把 Document.content 转回 bytes 给下一站时用。"""
    return content.encode()


def decode_bytes(
    content: bytes,
    encodings: List[str] = None,
) -> str:
    """bytes → str，自动尝试多个编码。

    顺序敏感：UTF-8 优先 → 中文编码（gb18030 是 GBK 超集，放前）→ latin-1 兜底。
    所有编码都失败时，用 latin-1 + errors="replace"，可能产生乱码但不抛异常。
    """
    if encodings is None:
        encodings = [
            "utf-8",
            "gb18030",
            "gb2312",
            "gbk",
            "big5",
            "ascii",
            "latin-1",
        ]

    for encoding in encodings:
        try:
            text = content.decode(encoding)
            logger.debug("decode_bytes: success with %s, %d chars", encoding, len(text))
            return text
        except UnicodeDecodeError:
            continue

    logger.warning(
        "decode_bytes: all encodings failed, falling back to latin-1 with replace. "
        "Output may contain replacement chars."
    )
    return content.decode("latin-1", errors="replace")
