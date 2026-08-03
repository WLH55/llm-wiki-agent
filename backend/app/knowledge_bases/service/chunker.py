"""
文本分块器（CJK 友好）

策略：
- 中英混排：CJK 字符按字算，其他按 5 字符 ≈ 1 word 估算
- 按句号切分（。.!?\n），尽量保留语义完整
- 单句超长时硬切
- overlap 保证上下文连续性
"""
import re
from typing import List

_DEFAULT_MAX_WORDS = 300
_DEFAULT_OVERLAP = 50

# 简单句号切分（中英文）
_SENTENCE_END = re.compile(r"[。\.!?！？\n]")


def chunk_text(
    text: str,
    max_words: int = _DEFAULT_MAX_WORDS,
    overlap: int = _DEFAULT_OVERLAP,
) -> List[str]:
    """CJK 友好分块

    Args:
        text: 原始文本
        max_words: 每块最大词数（CJK 1字 = 1，英文 5字 ≈ 1）
        overlap: 重叠词数（保留上下文）

    Returns:
        文本块列表
    """
    if not text or not text.strip():
        return []

    sentences = [s for s in _SENTENCE_END.split(text) if s and s.strip()]
    if not sentences:
        return []

    chunks: List[str] = []
    current = ""
    current_words = 0

    for sent in sentences:
        sent_words = _count_words(sent)

        # 单句超长：硬切
        if sent_words > max_words:
            if current:
                chunks.append(current.strip())
                current = ""
                current_words = 0
            for piece in _hard_split(sent, max_words):
                chunks.append(piece.strip())
            continue

        # 累加后超长：当前块结束，开新块（带 overlap）
        if current_words + sent_words > max_words:
            chunks.append(current.strip())
            tail = _tail_words(current, overlap)
            current = (tail + " " + sent).strip()
            current_words = _count_words(current)
        else:
            current = (current + " " + sent).strip()
            current_words += sent_words

    if current.strip():
        chunks.append(current.strip())

    return chunks


def _count_words(text: str) -> int:
    """CJK 字符按 1 计，其他按 5 字符 ≈ 1 word"""
    cjk = sum(1 for c in text if "一" <= c <= "鿿")
    other = len(text) - cjk
    return cjk + other // 5


def _hard_split(text: str, max_words: int) -> List[str]:
    """硬切（按字符数等分）"""
    step = max_words * 5
    return [text[i:i + step] for i in range(0, len(text), step)]


def _tail_words(text: str, n: int) -> str:
    """取末尾 n 个 word 的文本（粗略）"""
    if n <= 0 or not text:
        return ""
    chars = n * 5
    return text[-chars:] if len(text) > chars else text
