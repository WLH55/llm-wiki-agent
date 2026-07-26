"""MarkdownParser 升级版契约测试：表格标准化 + base64 图片抽取。"""
import base64
import re

from app.parsers.core.document import Document
from app.parsers.implementations.markdown import (
    MarkdownImageBase64,
    MarkdownParser,
    MarkdownTableFormatter,
    MarkdownTableUtil,
)


class TestMarkdownTableFormatter:
    """表格标准化阶段。"""

    def test_normalizes_spacing_and_alignment(self):
        """歪斜表格应标准化为 GFM 间距/对齐。"""
        raw = (
            "|姓名|年龄|城市|\n"
            "|:---|---:|:---:|\n"
            "|张三|25|北京|\n"
        )
        doc = MarkdownTableFormatter().parse(raw.encode("utf-8"))
        assert "| 姓名 | 年龄 | 城市 |" in doc.content
        assert "| :--- | ---: | :---: |" in doc.content
        assert "| 张三 | 25 | 北京 |" in doc.content

    def test_fixes_markitdown_spurious_prefix(self):
        """应清理伪空行/分隔前缀，并补齐 GFM 分隔行。"""
        raw = (
            "|  |  |\n"
            "| --- | --- |\n"
            "| A | B |\n"
            "| 1 | 2 |\n"
        )
        util = MarkdownTableUtil()
        formatted = util.format_table(raw)
        lines = [line for line in formatted.splitlines() if line.strip()]
        assert lines[0] == "| A | B |"
        assert lines[1] == "| --- | --- |"
        assert lines[2] == "| 1 | 2 |"


class TestMarkdownImageBase64:
    """Base64 图片抽取阶段。"""

    def test_extracts_base64_image_and_replaces_with_path(self):
        """data URI 图片应被替换为 images/<uuid>.ext，并进入 images。"""
        png_b64 = base64.b64encode(b"fake-png-bytes").decode()
        raw = f"before ![logo](data:image/png;base64,{png_b64}) after"
        doc = MarkdownImageBase64().parse(raw.encode("utf-8"))
        assert "data:image/png;base64," not in doc.content
        assert "before" in doc.content and "after" in doc.content
        assert re.search(r"!\[logo\]\(images/[0-9a-f-]{36}\.png\)", doc.content)
        assert len(doc.images) == 1
        path, value = next(iter(doc.images.items()))
        assert path.startswith("images/")
        assert path.endswith(".png")
        assert base64.b64decode(value) == b"fake-png-bytes"

    def test_invalid_base64_falls_back_to_alt_text(self):
        """非法 base64 应跳过图片并保留 alt。"""
        raw = "x ![bad](data:image/png;base64,@@@) y"
        doc = MarkdownImageBase64().parse(raw.encode("utf-8"))
        assert doc.content == "x bad y"
        assert doc.images == {}


class TestMarkdownParserPipeline:
    """完整管道：表格 + 图片。"""

    def test_formats_table_and_extracts_image(self):
        """MarkdownParser 应同时完成表格标准化与图片抽取。"""
        png_b64 = base64.b64encode(b"img").decode()
        raw = (
            "|Name|Age|\n"
            "|---|---|\n"
            f"|John|30|\n\n"
            f"logo ![logo](data:image/png;base64,{png_b64})"
        )
        doc = MarkdownParser(file_name="a.md").parse(raw.encode("utf-8"))
        assert isinstance(doc, Document)
        assert "| Name | Age |" in doc.content
        assert "| --- | --- |" in doc.content
        assert "| John | 30 |" in doc.content
        assert "data:image/png;base64," not in doc.content
        assert len(doc.images) == 1
        assert next(iter(doc.images)).startswith("images/")

    def test_plain_markdown_still_works(self):
        """无表格无图片时保持纯文本透传。"""
        doc = MarkdownParser().parse(b"# title\n\nhello")
        assert doc.content == "# title\n\nhello"
        assert doc.images == {}
        assert doc.is_valid() is True

    def test_empty_content_is_invalid(self):
        """空内容 is_valid 为 False。"""
        doc = MarkdownParser().parse(b"")
        assert doc.content == ""
        assert doc.is_valid() is False

    def test_handles_chinese_and_gbk(self):
        """中文与 GBK 编码可正确解码。"""
        doc = MarkdownParser().parse("# 标题".encode("utf-8"))
        assert doc.content == "# 标题"
        doc_gbk = MarkdownParser().parse("你好".encode("gbk"))
        assert doc_gbk.content == "你好"
