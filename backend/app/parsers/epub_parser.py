"""EPUB 电子书解析器。"""

import base64
import logging
import os
import posixpath
import re
import tempfile
import zipfile
from io import BytesIO
from typing import Any
from urllib.parse import unquote

import ebooklib
from bs4 import BeautifulSoup
from ebooklib import epub

from app.parsers.base import BaseParser
from app.parsers.document import Document
from app.parsers.web_parser import html_to_markdown

logger = logging.getLogger(__name__)

MAX_EPUB_MEMBER_SIZE = 32 * 1024 * 1024
MAX_EPUB_TOTAL_SIZE = 128 * 1024 * 1024
MAX_EPUB_COMPRESSION_RATIO = 100
MAX_EPUB_ENTRIES = 10_000


def validate_epub_archive(content: bytes) -> None:
    """验证 EPUB 结构和 ZIP 解压资源上限。"""

    source = BytesIO(content)
    if not zipfile.is_zipfile(source):
        raise ValueError("invalid_epub_archive")

    with zipfile.ZipFile(source, "r") as archive:
        members = archive.infolist()
        if len(members) > MAX_EPUB_ENTRIES:
            raise ValueError("epub_too_many_entries")

        total_size = 0
        for member in members:
            if member.file_size > MAX_EPUB_MEMBER_SIZE:
                raise ValueError(f"epub_member_too_large: {member.filename}")
            total_size += member.file_size
            if total_size > MAX_EPUB_TOTAL_SIZE:
                raise ValueError("epub_total_size_too_large")
            ratio = member.file_size / max(member.compress_size, 1)
            if ratio > MAX_EPUB_COMPRESSION_RATIO:
                raise ValueError(
                    f"epub_compression_ratio_too_large: {member.filename}"
                )

        names = {member.filename.replace("\\", "/") for member in members}
        if "mimetype" not in names or "META-INF/container.xml" not in names:
            raise ValueError("invalid_epub_archive: missing required files")
        media_type = archive.read("mimetype").decode("ascii", errors="replace").strip()
        if media_type != "application/epub+zip":
            raise ValueError("invalid_epub_archive: invalid mimetype")


class EPUBParser(BaseParser):
    """按电子书 spine 顺序提取章节、元数据和内嵌图片。"""

    def __init__(
        self,
        *args: Any,
        extract_images: bool = True,
        **kwargs: Any,
    ):
        super().__init__(*args, **kwargs)
        self.extract_images = extract_images

    def parse_into_text(self, content: bytes) -> Document:
        """将 EPUB bytes 转换为 Markdown Document。"""

        try:
            validate_epub_archive(content)
            book = self._read_book(content)
            metadata = self._extract_metadata(book)
            images, aliases = self._extract_images(book)
            chapters = self._extract_chapters(book, aliases)
        except Exception as exc:
            logger.error("打开 EPUB 失败：%s", exc)
            return Document(
                content="",
                metadata={"format": "epub", "error": f"open_failed: {exc}"},
            )

        metadata.update(
            {
                "format": "epub",
                "file_size": len(content),
                "chapter_count": len(chapters),
                "image_count": len(images),
            }
        )
        return Document(
            content="\n\n".join(chapters),
            images=images,
            metadata=metadata,
        )

    @staticmethod
    def _read_book(content: bytes):
        """ebooklib 需要文件路径，因此使用可清理的临时文件。"""

        path = ""
        try:
            with tempfile.NamedTemporaryFile(
                suffix=".epub",
                delete=False,
                mode="wb",
            ) as temporary_file:
                temporary_file.write(content)
                path = temporary_file.name
            return epub.read_epub(path)
        finally:
            if path and os.path.exists(path):
                os.unlink(path)

    @staticmethod
    def _extract_metadata(book) -> dict[str, str]:
        """把 Dublin Core 元数据映射到统一字段。"""

        mapping = {
            "title": "title",
            "creator": "author",
            "language": "language",
            "publisher": "publisher",
            "identifier": "identifier",
        }
        metadata: dict[str, str] = {}
        for source_key, target_key in mapping.items():
            values = book.get_metadata("DC", source_key)
            if not values:
                continue
            texts = [str(value[0]).strip() for value in values if value and value[0]]
            if texts:
                metadata[target_key] = ", ".join(texts) if target_key == "author" else texts[0]
        return metadata

    def _extract_images(self, book) -> tuple[dict[str, str], dict[str, str]]:
        """提取 EPUB 图片，并建立章节内相对路径到文档路径的映射。"""

        if not self.extract_images:
            return {}, {}

        images: dict[str, str] = {}
        aliases: dict[str, str] = {}
        for item in book.get_items_of_type(ebooklib.ITEM_IMAGE):
            original_path = item.get_name()
            image_path = self._unique_image_path(original_path, images)
            images[image_path] = base64.b64encode(item.get_content()).decode("ascii")
            self._add_image_aliases(aliases, original_path, image_path)
        return images, aliases

    def _extract_chapters(self, book, image_aliases: dict[str, str]) -> list[str]:
        """优先使用 spine 顺序，无可用 spine 时回退文档项顺序。"""

        documents = [
            item
            for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT)
            if not isinstance(item, epub.EpubNav)
        ]
        by_id = {item.get_id(): item for item in documents}
        ordered = []
        seen: set[str] = set()

        for spine_entry in book.spine:
            item_id = spine_entry[0] if isinstance(spine_entry, tuple) else spine_entry
            item = by_id.get(item_id)
            if item is not None and item.get_id() not in seen:
                ordered.append(item)
                seen.add(item.get_id())
        for item in documents:
            if item.get_id() not in seen:
                ordered.append(item)

        chapters = []
        for index, item in enumerate(ordered, start=1):
            chapter = self._process_chapter(item, index, image_aliases)
            if chapter:
                chapters.append(chapter)
        return chapters

    @staticmethod
    def _process_chapter(
        item,
        index: int,
        image_aliases: dict[str, str],
    ) -> str:
        """提取单章标题和正文。"""

        soup = BeautifulSoup(item.get_content(), "lxml")
        heading = soup.find(["h1", "h2"])
        if heading is not None:
            title = heading.get_text(" ", strip=True)
            heading.decompose()
        elif soup.title and soup.title.string:
            title = soup.title.string.strip()
        else:
            stem = posixpath.basename(item.get_name()).rsplit(".", 1)[0]
            title = re.sub(r"[_-]+", " ", stem).strip().title()
        title = title or f"Chapter {index}"
        body_html = str(soup.body) if soup.body else str(soup)
        markdown = html_to_markdown(
            body_html,
            image_aliases=image_aliases,
            base_location=item.get_name(),
        )
        return f"## {title}\n\n{markdown}" if markdown else f"## {title}"

    @staticmethod
    def _unique_image_path(
        original_path: str,
        images: dict[str, str],
    ) -> str:
        """生成不带 EPUB 内部目录且不重复的图片路径。"""

        filename = posixpath.basename(EPUBParser._normalize_path(original_path))
        filename = re.sub(r"[^A-Za-z0-9._-]+", "_", filename).strip("._")
        filename = filename or "image.bin"
        candidate = f"images/{filename}"
        if candidate not in images:
            return candidate
        stem, extension = posixpath.splitext(filename)
        suffix = 2
        while f"images/{stem}_{suffix}{extension}" in images:
            suffix += 1
        return f"images/{stem}_{suffix}{extension}"

    @staticmethod
    def _add_image_aliases(
        aliases: dict[str, str],
        original_path: str,
        image_path: str,
    ) -> None:
        """登记 EPUB 图片路径的编码和相对路径形式。"""

        normalized = EPUBParser._normalize_path(original_path)
        for alias in {
            original_path,
            unquote(original_path),
            normalized,
            posixpath.basename(normalized),
        }:
            if alias:
                aliases[alias] = image_path

    @staticmethod
    def _normalize_path(path: str) -> str:
        """规范 EPUB 内部 POSIX 路径。"""

        decoded = unquote(path).split("#", 1)[0].split("?", 1)[0]
        normalized = posixpath.normpath(decoded.replace("\\", "/"))
        return "" if normalized == "." else normalized.lstrip("/")
