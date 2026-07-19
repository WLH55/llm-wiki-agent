"""解析 MHTML 网页归档及其中的内嵌图片。"""

import base64
import email
import html
import logging
import os
import re
import uuid
from dataclasses import dataclass
from email.message import Message
from typing import Any
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup

from app.parsers.base import BaseParser
from app.parsers.document import Document
from app.parsers.web_parser import html_to_markdown

logger = logging.getLogger(__name__)

_AD_DOMAINS = (
    "googleads",
    "doubleclick",
    "googlesyndication",
    "facebook.com/tr",
    "analytics",
    "pixel",
)


@dataclass(frozen=True)
class _HtmlPart:
    """一个 MHTML HTML 部件。"""

    content: str
    location: str


class MHTMLParser(BaseParser):
    """将 MIME HTML 网页归档转换为 Markdown 文档。"""

    def __init__(
        self,
        *args: Any,
        extract_images: bool = True,
        **kwargs: Any,
    ):
        super().__init__(*args, **kwargs)
        self.extract_images = extract_images

    def parse_into_text(self, content: bytes) -> Document:
        """解析 MHTML 主正文，并按配置提取图片。"""

        message = email.message_from_bytes(content)
        html_parts: list[_HtmlPart] = []
        images: dict[str, str] = {}
        image_aliases: dict[str, str] = {}

        for part in message.walk():
            content_type = part.get_content_type()
            if content_type == "text/html":
                decoded = self._decode_html_part(part)
                if decoded:
                    html_parts.append(
                        _HtmlPart(
                            content=decoded,
                            location=(part.get("Content-Location") or "").strip(),
                        )
                    )
            elif content_type.startswith("image/") and self.extract_images:
                self._extract_image_part(part, content_type, images, image_aliases)

        main_part = self._select_main_html(html_parts)
        if main_part is None:
            return Document(
                content="",
                images=images,
                metadata={
                    "format": "mhtml",
                    "file_size": len(content),
                    "image_count": len(images),
                    "error": "no_html_content",
                },
            )

        markdown_text = html_to_markdown(
            main_part.content,
            image_aliases=image_aliases,
            base_location=main_part.location,
        )
        title = self._extract_title(main_part.content)
        metadata: dict[str, Any] = {
            "format": "mhtml",
            "file_size": len(content),
            "image_count": len(images),
        }
        if title:
            metadata["title"] = title
        if main_part.location:
            metadata["source_url"] = main_part.location
        return Document(content=markdown_text, images=images, metadata=metadata)

    @staticmethod
    def _decode_html_part(part: Message) -> str:
        """按 MIME 声明的字符集解码 HTML 部件。"""

        payload = part.get_payload(decode=True)
        if not payload:
            return ""
        charset = part.get_content_charset() or "utf-8"
        try:
            return payload.decode(charset, errors="replace")
        except LookupError:
            return payload.decode("utf-8", errors="replace")

    def _extract_image_part(
        self,
        part: Message,
        content_type: str,
        images: dict[str, str],
        image_aliases: dict[str, str],
    ) -> None:
        """提取一个图片部件，并登记所有可能的引用形式。"""

        image_data = part.get_payload(decode=True)
        if not image_data:
            return
        image_path = self._image_path_for_part(part, content_type, images)
        images[image_path] = base64.b64encode(image_data).decode("ascii")
        self._add_image_aliases(image_aliases, part, image_path)

    @staticmethod
    def _select_main_html(html_parts: list[_HtmlPart]) -> _HtmlPart | None:
        """选择体积最大的非广告 HTML 部件。"""

        if not html_parts:
            return None
        non_ad_parts = [
            part
            for part in html_parts
            if not any(domain in part.location.lower() for domain in _AD_DOMAINS)
        ]
        candidates = non_ad_parts or html_parts
        return max(candidates, key=lambda part: len(part.content))

    @staticmethod
    def _add_image_aliases(
        image_aliases: dict[str, str],
        part: Message,
        image_path: str,
    ) -> None:
        """登记 CID、附件 ID 和 Content-Location 的多种写法。"""

        for raw_value in (
            part.get("Content-Location") or "",
            part.get("Content-ID") or "",
            part.get("X-Attachment-Id") or "",
        ):
            raw_value = raw_value.strip()
            if not raw_value:
                continue
            decoded = unquote(html.unescape(raw_value))
            aliases = {raw_value, html.unescape(raw_value), decoded}
            cid = raw_value.strip("<>")
            if cid:
                aliases.update({f"cid:{cid}", f"cid:{unquote(cid)}"})
            for alias in aliases:
                if alias:
                    image_aliases[alias] = image_path

    @classmethod
    def _image_path_for_part(
        cls,
        part: Message,
        content_type: str,
        images: dict[str, str],
    ) -> str:
        """优先从原始位置或 CID 生成稳定且安全的图片路径。"""

        extension = cls._image_extension(content_type)
        location = (part.get("Content-Location") or "").strip()
        filename = cls._filename_from_location(location)
        if not filename:
            content_id = (part.get("Content-ID") or "").strip("<> ")
            safe_id = re.sub(r"[^A-Za-z0-9._-]+", "_", content_id).strip("._")
            filename = safe_id or uuid.uuid4().hex
        stem, current_extension = os.path.splitext(filename)
        if not current_extension:
            filename = f"{filename}{extension}"
        image_path = f"images/{filename}"
        if image_path not in images:
            return image_path

        stem, current_extension = os.path.splitext(filename)
        suffix = 2
        while f"images/{stem}_{suffix}{current_extension}" in images:
            suffix += 1
        return f"images/{stem}_{suffix}{current_extension}"

    @staticmethod
    def _filename_from_location(location: str) -> str:
        """从 Content-Location 中读取不含目录的文件名。"""

        decoded = unquote(html.unescape(location.strip()))
        if not decoded or decoded.lower().startswith("cid:"):
            return ""
        filename = os.path.basename(urlparse(decoded).path or decoded)
        if not filename or filename in {".", ".."} or "/" in filename or "\\" in filename:
            return ""
        return filename

    @staticmethod
    def _image_extension(content_type: str) -> str:
        """把常见 MIME 图片类型映射为扩展名。"""

        return {
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/gif": ".gif",
            "image/webp": ".webp",
            "image/bmp": ".bmp",
            "image/tiff": ".tiff",
            "image/x-icon": ".ico",
        }.get(content_type, ".bin")

    @staticmethod
    def _extract_title(html_content: str) -> str:
        """读取主 HTML 的标题。"""

        soup = BeautifulSoup(html_content, "lxml")
        if soup.title and soup.title.string:
            return soup.title.string.strip()
        return ""
