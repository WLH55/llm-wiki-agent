"""Markdown 解析：表格标准化 + Base64 图片抽取 + 管道组合。

阶段拆分：
1. MarkdownTableFormatter：GFM 表格规范化
2. MarkdownImageBase64：抽取 data URI 图片到 Document.images
3. MarkdownParser：PipelineParser 串联以上两阶段
"""
import base64
import logging
import re
import uuid
from typing import Dict, List, Match, Optional, Tuple

from app.parsers.core.base import BaseParser
from app.parsers.core.chain import PipelineParser
from app.parsers.core.document import Document
from app.parsers.utils import encoding

logger = logging.getLogger(__name__)

_SEPARATOR_CELL = re.compile(r"^:?-{3,}:?$")


class MarkdownTableUtil:
    """Markdown 表格标准化工具。

    能力：
    - 对齐行/数据行空格规范化
    - 清理 MarkItDown 伪前缀空行/分隔行
    - 为无分隔行的表格补 GFM delimiter
    """

    def __init__(self):
        self.align_pattern = re.compile(
            r"^([\t ]*)\|[\t ]*[:-]+(?:[\t ]*\|[\t ]*[:-]+)*[\t ]*\|[\t ]*$",
            re.MULTILINE,
        )
        self.line_pattern = re.compile(
            r"^([\t ]*)\|[\t ]*[^|\r\n]*(?:[\t ]*\|[^|\r\n]*)*\|[\t ]*$",
            re.MULTILINE,
        )

    @staticmethod
    def _split_row_cells(row_line: str) -> List[str]:
        """按 | 切分表格行，保留空单元格。"""
        inner = row_line.strip()
        if not inner.startswith("|"):
            return []
        parts = inner.split("|")
        if parts and parts[0].strip() == "":
            parts = parts[1:]
        if parts and parts[-1].strip() == "":
            parts = parts[:-1]
        return [part.strip() for part in parts]

    @staticmethod
    def _is_table_row(line: str) -> bool:
        """判断是否为 markdown 表格行。"""
        stripped = line.strip()
        return stripped.startswith("|") and "|" in stripped[1:]

    @classmethod
    def _is_separator_row(cls, line: str) -> bool:
        """判断是否为对齐分隔行。"""
        cells = cls._split_row_cells(line)
        return bool(cells) and all(_SEPARATOR_CELL.match(cell) for cell in cells)

    @classmethod
    def _is_empty_row(cls, line: str) -> bool:
        """判断是否为空表格行。"""
        cells = cls._split_row_cells(line)
        return bool(cells) and all(cell == "" for cell in cells)

    @classmethod
    def _separator_row_for(cls, header_line: str) -> str:
        """根据表头列数生成默认分隔行。"""
        cells = cls._split_row_cells(header_line)
        return "| " + " | ".join("---" for _ in cells) + " |"

    @classmethod
    def _normalize_table_block(cls, block: List[str]) -> List[str]:
        """规范化单个表格块：去伪前缀，并保证 GFM 分隔行。"""
        while block and cls._is_empty_row(block[0]):
            block.pop(0)
        if block and cls._is_separator_row(block[0]):
            block.pop(0)
        if len(block) >= 2 and not cls._is_separator_row(block[1]):
            sep = cls._separator_row_for(block[0])
            block = [block[0], sep] + block[1:]
        return block

    def normalize_spurious_table_prefixes(self, content: str) -> str:
        """清理 MarkItDown 风格表格的伪前缀行。"""
        lines = content.split("\n")
        out: List[str] = []
        i = 0
        while i < len(lines):
            line = lines[i]
            if not self._is_table_row(line):
                out.append(line)
                i += 1
                continue
            block: List[str] = []
            while i < len(lines) and self._is_table_row(lines[i]):
                block.append(lines[i])
                i += 1
            out.extend(self._normalize_table_block(block))
        return "\n".join(out)

    def format_table(self, content: str) -> str:
        """格式化全文中的 markdown 表格。"""

        def process_align(match: Match[str]) -> str:
            """规范化对齐行。"""
            columns = self._split_row_cells(match.group(0))
            processed = []
            for col in columns:
                left_colon = ":" if col.startswith(":") else ""
                right_colon = ":" if col.endswith(":") else ""
                processed.append(left_colon + "---" + right_colon)
            prefix = match.group(1)
            return prefix + "| " + " | ".join(processed) + " |"

        def process_line(match: Match[str]) -> str:
            """规范化普通表格行。"""
            columns = self._split_row_cells(match.group(0))
            prefix = match.group(1)
            return prefix + "| " + " | ".join(columns) + " |"

        formatted_content = self.line_pattern.sub(process_line, content)
        formatted_content = self.align_pattern.sub(process_align, formatted_content)
        return self.normalize_spurious_table_prefixes(formatted_content)


class MarkdownTableFormatter(BaseParser):
    """表格标准化阶段 parser。"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.table_helper = MarkdownTableUtil()

    def parse_into_text(self, content: bytes) -> Document:
        """bytes → 标准化表格后的 Document。"""
        text = encoding.decode_bytes(content)
        text = self.table_helper.format_table(text)
        return Document(content=text)


class MarkdownImageUtil:
    """Markdown 图片工具：路径抽取、base64 抽取、路径替换。"""

    def __init__(self):
        self.b64_pattern = re.compile(
            r"!\[(.*?)\]\(data:image/([^;]+);base64,([^\)]+)\)"
        )
        self.image_pattern = re.compile(r"!\[(.*?)\]\(([^)]+)\)")
        self.replace_pattern = re.compile(r"!\[(.*?)\]\(([^)]+)\)")

    def extract_image(
        self,
        content: str,
        path_prefix: Optional[str] = None,
        replace: bool = True,
    ) -> Tuple[str, List[str]]:
        """抽取普通图片路径。"""
        images: List[str] = []

        def repl(match: Match[str]) -> str:
            title = match.group(1)
            image_path = match.group(2)
            if path_prefix:
                image_path = f"{path_prefix}/{image_path}"
            images.append(image_path)
            if not replace:
                return match.group(0)
            return f"![{title}]({image_path})"

        text = self.image_pattern.sub(repl, content)
        logger.debug("Extracted %d images from markdown", len(images))
        return text, images

    def extract_base64(
        self,
        content: str,
        path_prefix: Optional[str] = None,
        replace: bool = True,
    ) -> Tuple[str, Dict[str, bytes]]:
        """抽取 base64 内嵌图片，并可选替换为路径引用。"""
        images: Dict[str, bytes] = {}

        def repl(match: Match[str]) -> str:
            title = match.group(1)
            img_ext = match.group(2)
            img_b64 = match.group(3)
            image_byte = encoding.encode_image(img_b64, errors="ignore")
            if not image_byte:
                logger.error("Failed to decode base64 image, skip it")
                return title
            image_path = f"{uuid.uuid4()}.{img_ext}"
            if path_prefix:
                image_path = f"{path_prefix}/{image_path}"
            images[image_path] = image_byte
            if not replace:
                return match.group(0)
            return f"![{title}]({image_path})"

        text = self.b64_pattern.sub(repl, content)
        logger.debug("Extracted %d base64 images from markdown", len(images))
        return text, images

    def replace_path(self, content: str, images: Dict[str, str]) -> str:
        """按映射表替换图片路径。"""
        content_replace: set = set()

        def repl(match: Match[str]) -> str:
            title = match.group(1)
            image_path = match.group(2)
            if image_path not in images:
                return match.group(0)
            content_replace.add(image_path)
            new_path = images[image_path]
            return f"![{title}]({new_path})" if new_path else title

        text = self.replace_pattern.sub(repl, content)
        logger.debug("Replaced %d images in markdown", len(content_replace))
        return text


class MarkdownImageBase64(BaseParser):
    """Base64 图片抽取阶段 parser。"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.image_helper = MarkdownImageUtil()

    def parse_into_text(self, content: bytes) -> Document:
        """bytes → 文本路径引用 + images[base64]。"""
        text = encoding.decode_bytes(content)
        text, img_b64 = self.image_helper.extract_base64(text, path_prefix="images")
        images: Dict[str, str] = {}
        for ipath, raw_bytes in img_b64.items():
            images[ipath] = base64.b64encode(raw_bytes).decode()
        logger.debug("Extracted %d base64 images from markdown", len(images))
        return Document(content=text, images=images)


class MarkdownParser(PipelineParser):
    """完整 Markdown parser：表格标准化 → Base64 图片抽取。"""

    _parser_cls = (MarkdownTableFormatter, MarkdownImageBase64)
