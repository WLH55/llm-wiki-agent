"""MarkdownParser：阶段 1 最简版（仅 decode → Document）。

刻意保持与 TextParser 行为等价，**不做**任何格式处理。
目的：为 Step 19 升级为 PipelineParser(TableFormatter, ImageBase64Extractor)
留下"单 parser 长得太胖、需要拆成阶段用管道串起来"的对比基线。

升级路径预告（不在本 Step 实现）：
- Step 16：追加 MarkdownTableFormatter（GFM 表格标准化）
- Step 17：追加 MarkdownImageBase64Extractor（base64 图片抽取）
- Step 19：整体重写为 PipelineParser(TableFormatter, ImageBase64)
"""
from app.parsers._utils.endecode import decode_bytes
from app.parsers.base import BaseParser
from app.parsers.document import Document


class MarkdownParser(BaseParser):
    """Markdown parser 最简版：bytes → Document(content=decode(bytes))。

    与 TextParser 的差异仅在**类型身份**——后续扩展（表格/图片 utils）
    会挂到这个类上，而不是污染 TextParser。
    """

    def parse_into_text(self, content: bytes) -> Document:
        text = decode_bytes(content)
        return Document(content=text)
