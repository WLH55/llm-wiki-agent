"""网页正文提取与 HTML 到 Markdown 转换。"""

import html
import logging
import os
import re
from typing import Any
from urllib.parse import unquote, urljoin

from bs4 import BeautifulSoup
from lxml.etree import XPath
from markdownify import markdownify
from trafilatura import extract, utils, xpaths

from app.parsers.core.base import BaseParser
from app.parsers.core.document import Document
from app.parsers.utils.web_fetcher import ScrapeResult, scrape_url

logger = logging.getLogger(__name__)

_MIN_FALLBACK_TEXT_LENGTH = 50


def _patch_trafilatura_for_wechat() -> None:
    """扩展 Trafilatura 内部规则，使其识别微信公众号正文和图片。"""

    try:
        utils.IMAGE_EXTENSION = re.compile(
            r"[^\s]+\.(avif|bmp|gif|hei[cf]|jpe?g|png|webp)(\b|$)|"
            r"mmbiz\.qpic\.cn/[^\s]*wx_fmt=(jpeg|jpg|png|gif|webp)",
            re.IGNORECASE,
        )
        wechat_body = XPath(
            '(.//*[@id="js_content" or contains(@class, "rich_media_content")])[1]'
        )
        if not any(str(item) == str(wechat_body) for item in xpaths.BODY_XPATH):
            xpaths.BODY_XPATH.insert(0, wechat_body)
    except (AttributeError, ImportError, TypeError) as exc:
        logger.warning("无法应用微信公众号 Trafilatura 兼容规则：%s", exc)


_patch_trafilatura_for_wechat()


def _prepare_wechat_html(html_content: str) -> str:
    """把微信懒加载图片的 data-src 提升为标准 src。"""

    soup = BeautifulSoup(html_content, "lxml")
    for image in soup.select("#js_content img, .rich_media_content img"):
        lazy_source = (image.get("data-src") or "").strip()
        if lazy_source:
            image["src"] = lazy_source
    return str(soup)


def _restore_missing_wechat_images(markdown_text: str, html_content: str) -> str:
    """补回 Trafilatura 仍可能过滤掉的微信无扩展名图片。"""

    soup = BeautifulSoup(html_content, "lxml")
    missing_images: list[str] = []
    for image in soup.select("#js_content img, .rich_media_content img"):
        source = (image.get("src") or "").strip()
        if not source or "mmbiz.qpic.cn" not in source or source in markdown_text:
            continue
        alt_text = (image.get("alt") or "图片").strip()
        missing_images.append(f"![{alt_text}]({source})")
    if not missing_images:
        return markdown_text
    return f"{markdown_text.rstrip()}\n\n" + "\n\n".join(missing_images)


def extract_markdown_from_html(html_content: str) -> str | None:
    """使用 Trafilatura 从 HTML 中抽取正文 Markdown。"""

    if not html_content or not html_content.strip():
        return None
    prepared_html = _prepare_wechat_html(html_content)
    markdown_text = extract(
        prepared_html,
        output_format="markdown",
        with_metadata=True,
        include_images=True,
        include_tables=True,
        include_links=True,
    )
    if not markdown_text or not markdown_text.strip():
        return None
    return _restore_missing_wechat_images(markdown_text.strip(), prepared_html)


def build_visible_text_fallback(
    visible_text: str,
    page_title: str = "",
) -> str | None:
    """当正文算法无结果时，用浏览器可见文本构造 Markdown。"""

    text = (visible_text or "").strip()
    if len(text) < _MIN_FALLBACK_TEXT_LENGTH:
        return None
    title = (page_title or "").strip()
    if title and not text.startswith(title):
        return f"# {title}\n\n{text}"
    return text


def _normalize_markdown(markdown_text: str) -> str:
    """统一换行并把连续空行压缩为一个空行。"""

    text = markdown_text.replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"\n[ \t]*\n(?:[ \t]*\n)+", "\n\n", text).strip()


def _rewrite_image_sources(
    soup: BeautifulSoup,
    image_aliases: dict[str, str],
    base_location: str,
) -> None:
    """把 MHTML 图片的 CID 或 Content-Location 替换为文档内路径。"""

    for image in soup.find_all("img"):
        source = (image.get("src") or "").strip()
        if not source:
            continue
        decoded_source = unquote(html.unescape(source))
        candidates = [source, html.unescape(source), decoded_source]
        if base_location:
            candidates.append(urljoin(base_location, source))
        base_name = os.path.basename(decoded_source)
        if base_name:
            candidates.append(base_name)
        for candidate in candidates:
            if candidate in image_aliases:
                image["src"] = image_aliases[candidate]
                break


def html_to_markdown(
    html_content: str,
    image_aliases: dict[str, str] | None = None,
    base_location: str = "",
) -> str:
    """把 HTML 转成 Markdown，并按需重写 MHTML 内嵌图片引用。"""

    soup = BeautifulSoup(html_content, "lxml")
    for tag in soup(["script", "style", "noscript", "iframe"]):
        tag.decompose()

    for link in soup.find_all("a"):
        target = (link.get("href") or "").strip().lower()
        if not target.startswith(("http://", "https://", "mailto:", "tel:")):
            link.unwrap()

    if image_aliases:
        _rewrite_image_sources(soup, image_aliases, base_location)

    visible_text = soup.get_text(separator="\n", strip=True)
    converted = _normalize_markdown(markdownify(str(soup), heading_style="ATX"))
    if converted:
        return converted
    if visible_text:
        return visible_text
    return f"```html\n{html_content[:50_000]}\n```"


def _decode_html(content: bytes) -> str:
    """按常见网页编码解码本地 HTML。"""

    for encoding in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def _html_title(html_content: str) -> str:
    """读取 HTML title 元素。"""

    soup = BeautifulSoup(html_content, "lxml")
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    return ""


def _looks_like_url(content: bytes) -> bool:
    """判断输入是否是 Parser 契约中的 URL bytes。"""

    try:
        value = content.decode("utf-8").strip()
    except UnicodeDecodeError:
        return False
    return value.startswith(("http://", "https://")) and "\n" not in value


class WebParser(BaseParser):
    """解析本地 HTML，或抓取 URL 后解析渲染后的网页。"""

    def __init__(self, title: str = "", **kwargs: Any):
        self.title = title
        kwargs.setdefault("file_name", title)
        super().__init__(**kwargs)

    def parse_into_text(self, content: bytes) -> Document:
        """将 HTML bytes 或 URL bytes 转换为 Document。"""

        if _looks_like_url(content):
            return self._parse_url(content.decode("utf-8").strip())
        return self._parse_local_html(content)

    def _parse_url(self, url: str) -> Document:
        """抓取并解析远程网页。"""

        try:
            result = scrape_url(url)
        except Exception as exc:
            logger.error("抓取网页失败：%s", exc)
            return Document(
                content="",
                metadata={"format": "html", "source_url": url, "error": str(exc)},
            )

        markdown_text = extract_markdown_from_html(result.html)
        if not markdown_text:
            markdown_text = build_visible_text_fallback(
                result.visible_text,
                result.page_title,
            )
        if not markdown_text:
            markdown_text = html_to_markdown(result.html)

        return Document(
            content=markdown_text,
            metadata=self._remote_metadata(result),
        )

    def _parse_local_html(self, content: bytes) -> Document:
        """解析已经下载到本地的 HTML bytes。"""

        html_content = _decode_html(content)
        title = _html_title(html_content) or self.title
        markdown_text = extract_markdown_from_html(html_content)
        if not markdown_text:
            markdown_text = html_to_markdown(html_content)
        return Document(
            content=markdown_text,
            metadata={"format": "html", "title": title},
        )

    def _remote_metadata(self, result: ScrapeResult) -> dict[str, str]:
        """构造远程网页元数据。"""

        return {
            "format": "html",
            "source_url": result.url,
            "final_url": result.final_url,
            "title": result.page_title or self.title,
        }
