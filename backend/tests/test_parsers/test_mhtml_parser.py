"""MHTML 网页归档解析契约测试。"""

from email.message import EmailMessage
from importlib import import_module

import pytest

from app.parsers.core.base import BaseParser


def _mhtml_module():
    try:
        return import_module("app.parsers.implementations.mhtml")
    except ModuleNotFoundError:
        pytest.fail("缺少计划模块：app.parsers.implementations.mhtml")


def _mhtml_bytes() -> bytes:
    root = EmailMessage()
    root["Subject"] = "网页归档"
    root.make_related()
    main = EmailMessage()
    main.set_content(
        "<html><head><title>主文章</title></head><body>"
        "<h1>主文章</h1><p>这是 MHTML 正文。</p>"
        '<a href="https://example.com">外部链接</a>'
        '<img src="cid:article-image" alt="内嵌图片">'
        "<script>window.noise = true</script></body></html>",
        subtype="html",
    )
    main["Content-Location"] = "https://example.com/article"
    root.attach(main)
    advertisement = EmailMessage()
    advertisement.set_content("<html><body><h1>广告内容</h1></body></html>", subtype="html")
    advertisement["Content-Location"] = "https://googleads.example/frame"
    root.attach(advertisement)
    image = EmailMessage()
    image.set_content(b"\x89PNG\r\n\x1a\n", maintype="image", subtype="png")
    image["Content-ID"] = "<article-image>"
    root.attach(image)
    return root.as_bytes()


def test_mhtml_parser_extracts_main_html_and_embedded_image():
    module = _mhtml_module()
    assert issubclass(module.MHTMLParser, BaseParser)
    document = module.MHTMLParser(file_name="article.mhtml").parse(_mhtml_bytes())
    assert "主文章" in document.content
    assert "MHTML 正文" in document.content
    assert "[外部链接](https://example.com)" in document.content
    assert "广告内容" not in document.content
    assert "window.noise" not in document.content
    assert "cid:article-image" not in document.content
    assert len(document.images) == 1
    image_path = next(iter(document.images))
    assert image_path in document.content
    assert document.metadata["format"] == "mhtml"
    assert document.metadata["image_count"] == 1


def test_mhtml_parser_can_skip_images():
    module = _mhtml_module()
    document = module.MHTMLParser(
        file_name="article.mht", extract_images=False
    ).parse(_mhtml_bytes())
    assert document.images == {}


def test_registry_routes_mhtml_and_mht():
    module = _mhtml_module()
    from app.parsers import registry
    assert registry.get_parser_class("mhtml") is module.MHTMLParser
    assert registry.get_parser_class("mht") is module.MHTMLParser
