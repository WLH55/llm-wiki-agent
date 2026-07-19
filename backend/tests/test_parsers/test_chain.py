"""FirstParser / PipelineParser 契约测试。"""
from app.parsers.base import BaseParser
from app.parsers.chain import FirstParser, PipelineParser
from app.parsers.document import Document


class _AlwaysFailParser(BaseParser):
    """始终返回空文档。"""

    def parse_into_text(self, content: bytes) -> Document:
        return Document()


class _RaiseParser(BaseParser):
    """始终抛异常。"""

    def parse_into_text(self, content: bytes) -> Document:
        raise RuntimeError("boom")


class _OkParser(BaseParser):
    """返回固定成功内容。"""

    def parse_into_text(self, content: bytes) -> Document:
        return Document(content="ok", metadata={"stage": "ok"})


class _PrefixParser(BaseParser):
    """给内容加前缀，并写入 metadata/images。"""

    def parse_into_text(self, content: bytes) -> Document:
        text = content.decode("utf-8")
        return Document(
            content=f"A:{text}",
            images={"a.png": "aaa"},
            metadata={"from": "A"},
        )


class _SuffixParser(BaseParser):
    """给内容加后缀，并合并新 images/metadata。"""

    def parse_into_text(self, content: bytes) -> Document:
        text = content.decode("utf-8")
        return Document(
            content=f"{text}:B",
            images={"b.png": "bbb"},
            metadata={"stage": "B"},
        )


def test_first_parser_returns_first_valid_result():
    """责任链应跳过失败/异常 parser，返回首个有效结果。"""
    parser_cls = FirstParser.create(_AlwaysFailParser, _RaiseParser, _OkParser)
    doc = parser_cls().parse(b"ignored")
    assert doc.content == "ok"
    assert doc.metadata["stage"] == "ok"


def test_first_parser_returns_empty_when_all_fail():
    """全部失败时返回空 Document。"""
    parser_cls = FirstParser.create(_AlwaysFailParser, _RaiseParser)
    doc = parser_cls().parse(b"ignored")
    assert doc.content == ""
    assert doc.is_valid() is False


def test_pipeline_parser_chains_content_and_merges_side_effects():
    """管道应串内容，并合并各阶段 images/metadata。"""
    parser_cls = PipelineParser.create(_PrefixParser, _SuffixParser)
    doc = parser_cls().parse(b"raw")
    assert doc.content == "A:raw:B"
    assert doc.images == {"a.png": "aaa", "b.png": "bbb"}
    assert doc.metadata == {"from": "A", "stage": "B"}
