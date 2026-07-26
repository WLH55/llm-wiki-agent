"""Document 数据契约测试。"""
from app.parsers.core.document import Document


def test_empty_document_is_invalid():
    """空 Document 的 is_valid() 应为 False。"""
    doc = Document()
    assert doc.content == ""
    assert doc.images == {}
    assert doc.metadata == {}
    assert doc.is_valid() is False


def test_document_with_content_is_valid():
    """有 content 的 Document 是有效的。"""
    doc = Document(content="hello world")
    assert doc.is_valid() is True


def test_document_with_images_and_metadata():
    """images 和 metadata 默认空 dict，可填充。"""
    doc = Document(
        content="![img](images/a.png)",
        images={"images/a.png": "iVBORw0KGgo..."},
        metadata={"title": "Test", "page_count": 5},
    )
    assert doc.is_valid() is True
    assert "images/a.png" in doc.images
    assert doc.metadata["page_count"] == 5


def test_document_metadata_empty_string_still_invalid():
    """content='' 时即使 metadata 有值也是 invalid（is_valid 只看 content）。"""
    doc = Document(content="", metadata={"title": "Empty"})
    assert doc.is_valid() is False


def test_document_model_dump_roundtrip():
    """Pydantic 序列化往返。"""
    doc = Document(content="hello", metadata={"k": "v"})
    data = doc.model_dump()
    restored = Document(**data)
    assert restored == doc
