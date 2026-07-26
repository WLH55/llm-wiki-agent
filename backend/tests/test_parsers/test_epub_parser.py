"""EPUB 解析器契约测试。"""

import zipfile
from io import BytesIO

import pytest
from ebooklib import epub
from PIL import Image

from app.parsers import registry
from app.parsers.implementations.epub import EPUBParser, validate_epub_archive


def _png_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (2, 2), color="red").save(output, format="PNG")
    return output.getvalue()


def _epub_bytes(tmp_path) -> bytes:
    book = epub.EpubBook()
    book.set_identifier("learning-book-1")
    book.set_title("解析器学习")
    book.set_language("zh-CN")
    book.add_author("测试作者")

    first = epub.EpubHtml(title="第一章", file_name="text/first.xhtml", lang="zh-CN")
    first.content = (
        '<html><body><h1>第一章</h1><p>这是第一章正文。</p>'
        '<img src="../images/sample.png" alt="示例图"></body></html>'
    )
    second = epub.EpubHtml(title="第二章", file_name="text/second.xhtml", lang="zh-CN")
    second.content = "<html><body><h1>第二章</h1><p>这是第二章正文。</p></body></html>"
    image = epub.EpubItem(
        uid="sample-image",
        file_name="images/sample.png",
        media_type="image/png",
        content=_png_bytes(),
    )
    book.add_item(first)
    book.add_item(second)
    book.add_item(image)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.toc = (first, second)
    book.spine = [first, second]

    path = tmp_path / "sample.epub"
    epub.write_epub(path, book)
    return path.read_bytes()


def test_epub_parser_extracts_chapters_metadata_and_image(tmp_path):
    content = _epub_bytes(tmp_path)
    document = EPUBParser(file_name="sample.epub").parse(content)

    assert document.content.index("## 第一章") < document.content.index("## 第二章")
    assert "这是第一章正文" in document.content
    assert document.metadata["title"] == "解析器学习"
    assert document.metadata["author"] == "测试作者"
    assert document.metadata["language"] == "zh-CN"
    assert document.metadata["chapter_count"] == 2
    assert document.metadata["image_count"] == 1
    assert len(document.images) == 1
    image_path = next(iter(document.images))
    assert image_path in document.content


def test_epub_parser_can_skip_images(tmp_path):
    document = EPUBParser(
        file_name="sample.epub",
        extract_images=False,
    ).parse(_epub_bytes(tmp_path))
    assert document.images == {}
    assert document.metadata["image_count"] == 0


def test_epub_validator_rejects_high_compression_ratio():
    output = BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr("META-INF/container.xml", "<container/>")
        archive.writestr("large.txt", b"0" * 1_000_000)
    with pytest.raises(ValueError, match="epub_compression_ratio_too_large"):
        validate_epub_archive(output.getvalue())


def test_invalid_epub_returns_error_metadata():
    document = EPUBParser(file_name="broken.epub").parse(b"not an epub")
    assert document.content == ""
    assert document.metadata["error"].startswith("open_failed:")


def test_registry_routes_epub():
    assert registry.get_parser_class("builtin", "epub") is EPUBParser
