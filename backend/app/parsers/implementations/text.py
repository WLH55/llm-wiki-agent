"""TextParser：最简单的 parser，bytes → str，无格式处理。

用途：
1. 验证 BaseParser 抽象能工作
2. 未知扩展名（.log / .conf / .csv 等）兜底
3. 作为复杂 parser 的基线对比
"""
from app.parsers.core.base import BaseParser
from app.parsers.core.document import Document
from app.parsers.utils.encoding import decode_bytes


class TextParser(BaseParser):
    """文本 parser：bytes → Document(content=str)。

    自动用 BaseParser.__init__（file_name / file_type 推断）。
    """

    def parse_into_text(self, content: bytes) -> Document:
        text = decode_bytes(content)
        return Document(content=text)
