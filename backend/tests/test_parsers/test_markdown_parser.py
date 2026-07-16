"""MarkdownParser Stage 3 最简版契约测试。

刻意与 test_text_parser.py 等价：当前阶段 MarkdownParser 行为 == TextParser。
未来 Step 19 升级 PipelineParser 时，本测试需要重写。
"""
from app.parsers.document import Document
from app.parsers.markdown_parser import MarkdownParser


class TestMarkdownParserContract:
    """契约：bytes → Document(content=str, images={}, metadata={})。"""

    def test_parses_plain_markdown(self):
        parser = MarkdownParser(file_name="a.md")
        doc = parser.parse(b"# title\n\nhello world")
        assert doc.content == "# title\n\nhello world"
        assert doc.images == {}
        assert doc.metadata == {}

    def test_returns_document_instance(self):
        parser = MarkdownParser()
        doc = parser.parse(b"whatever")
        assert isinstance(doc, Document)

    def test_is_valid_when_content_present(self):
        parser = MarkdownParser()
        doc = parser.parse(b"hi")
        assert doc.is_valid() is True

    def test_is_valid_false_for_empty(self):
        parser = MarkdownParser()
        doc = parser.parse(b"")
        assert doc.content == ""
        assert doc.is_valid() is False

    def test_handles_chinese(self):
        parser = MarkdownParser(file_name="zh.md")
        doc = parser.parse("# 标题\n\n正文".encode("utf-8"))
        assert doc.content == "# 标题\n\n正文"

    def test_preserves_markdown_syntax(self):
        """Markdown 语法字符（# / * / | / []）应原样保留——本阶段不格式化。"""
        md = b"| col1 | col2 |\n| --- | --- |\n| **bold** | [link](url) |"
        parser = MarkdownParser()
        doc = parser.parse(md)
        assert doc.content == md.decode("utf-8")

    def test_decode_gbk_fallback(self):
        """GBK 编码的中文 markdown 也能被 fallback chain 解码。"""
        parser = MarkdownParser()
        doc = parser.parse("你好".encode("gbk"))
        assert doc.content == "你好"


class TestMarkdownParserVsTextParser:
    """行为等价验证：当前阶段两者输出完全一致。

    升级 Step 19 时删除本类——届时 MarkdownParser 会有格式化能力。
    """

    def test_same_output_for_same_input(self):
        from app.parsers.text_parser import TextParser

        payload = b"# title\n\nsome markdown content"
        md_doc = MarkdownParser().parse(payload)
        txt_doc = TextParser().parse(payload)
        assert md_doc.content == txt_doc.content
        assert md_doc.images == txt_doc.images
        assert md_doc.metadata == txt_doc.metadata
