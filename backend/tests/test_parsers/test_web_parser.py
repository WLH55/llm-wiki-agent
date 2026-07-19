"""网页抓取与 HTML 解析契约测试。"""

from importlib import import_module

import pytest

from app.parsers.base import BaseParser


def _web_module():
    try:
        return import_module("app.parsers.web_parser")
    except ModuleNotFoundError:
        pytest.fail("缺少计划模块：app.parsers.web_parser")


def _fetcher_module():
    try:
        return import_module("app.parsers.web_fetcher")
    except ModuleNotFoundError:
        pytest.fail("缺少计划模块：app.parsers.web_fetcher")


def test_url_validator_rejects_unsafe_targets():
    validate = _fetcher_module().validate_public_url
    for url in ("file:///etc/passwd", "http://127.0.0.1/a", "http://10.0.0.2/a"):
        with pytest.raises(ValueError, match="unsafe_url"):
            validate(url)
    assert validate("https://93.184.216.34/article") is None


def test_extracts_wechat_article_body_and_image_url():
    html = """
    <html><head><title>微信测试文章</title></head><body>
      <nav>导航噪声</nav>
      <div id="js_content" class="rich_media_content">
        <h1>微信测试文章</h1>
        <p>这是一段足够长的微信公众号正文，用来验证正文区域能够被准确识别和转换。</p>
        <img src="https://mmbiz.qpic.cn/example/image?wx_fmt=png" alt="示例图片">
      </div>
      <footer>页脚噪声</footer>
    </body></html>
    """
    markdown = _web_module().extract_markdown_from_html(html)
    assert markdown is not None
    assert "微信测试文章" in markdown
    assert "微信公众号正文" in markdown
    assert "mmbiz.qpic.cn" in markdown


def test_visible_text_fallback_adds_page_title():
    text = "这是动态网页渲染后的可见正文。" * 8
    markdown = _web_module().build_visible_text_fallback(text, "动态文章")
    assert markdown == f"# 动态文章\n\n{text}"


def test_web_parser_accepts_local_html_bytes():
    module = _web_module()
    assert issubclass(module.WebParser, BaseParser)
    html = b"<html><head><title>Local</title></head><body><article><h1>Hello</h1><p>World</p></article></body></html>"
    document = module.WebParser(file_name="article.html").parse(html)
    assert "Hello" in document.content
    assert "World" in document.content
    assert document.metadata["format"] == "html"
    assert document.metadata["title"] == "Local"


def test_web_parser_fetches_url_then_extracts_markdown(monkeypatch):
    module = _web_module()
    fetcher = _fetcher_module()
    result = fetcher.ScrapeResult(
        url="https://example.com/article",
        final_url="https://example.com/final",
        html="<html><body><article><h1>Fetched</h1><p>Remote body text.</p></article></body></html>",
        visible_text="Fetched\nRemote body text.",
        page_title="Fetched title",
    )
    monkeypatch.setattr(module, "scrape_url", lambda url: result)
    document = module.WebParser(title="").parse(b"https://example.com/article")
    assert "Fetched" in document.content
    assert document.metadata["source_url"] == "https://example.com/article"
    assert document.metadata["final_url"] == "https://example.com/final"
    assert document.metadata["title"] == "Fetched title"


def test_registry_routes_html_and_htm_to_web_parser():
    module = _web_module()
    from app.parsers import registry
    assert registry.get_parser_class("html") is module.WebParser
    assert registry.get_parser_class("htm") is module.WebParser
