"""OpenDataLoader PDF 高级解析器适配器。"""

import base64
import html
import logging
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from app.parsers.core.base import BaseParser
from app.parsers.core.document import Document

logger = logging.getLogger(__name__)

MIN_JAVA_MAJOR = 11
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff")
MARKDOWN_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")


def _load_opendataloader_module():
    """惰性导入 opendataloader_pdf，避免默认环境缺包时导入失败。"""

    import opendataloader_pdf

    return opendataloader_pdf


def _parse_java_major(version_text: str) -> int | None:
    """从 java -version 输出里解析主版本号。"""

    match = re.search(r'version\s+"(?P<version>\d+(?:\.\d+)*)', version_text)
    if match is None:
        match = re.search(r"\b(?P<version>\d+(?:\.\d+)*)\b", version_text)
    if match is None:
        return None
    parts = match.group("version").split(".")
    if parts[0] == "1" and len(parts) > 1:
        return int(parts[1])
    return int(parts[0])


def _java_available() -> tuple[bool, str]:
    """检查 Java 11+ 是否可用。"""

    if shutil.which("java") is None:
        return False, "java_not_found: 需要 Java 11+，请先安装并加入 PATH"
    try:
        result = subprocess.run(
            ["java", "-version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except Exception as exc:
        return False, f"java_check_failed: {exc}"
    output = f"{result.stdout}\n{result.stderr}"
    major = _parse_java_major(output)
    if major is None:
        return False, f"java_version_unknown: {output.strip()}"
    if major < MIN_JAVA_MAJOR:
        return False, f"java_too_old: 当前 Java {major}，需要 Java {MIN_JAVA_MAJOR}+"
    return True, ""


def _package_available() -> tuple[bool, str]:
    """检查 opendataloader-pdf Python 包是否可用。"""

    try:
        _load_opendataloader_module()
    except ImportError as exc:
        return False, f"opendataloader-pdf 未安装: {exc}"
    return True, ""


def opendataloader_available() -> tuple[bool, str]:
    """检查 OpenDataLoader 运行条件：Java 11+ 与 Python 包同时满足。"""

    ok, message = _java_available()
    if not ok:
        return ok, message
    return _package_available()


def _find_markdown_file(output_dir: str | Path, pdf_stem: str) -> Path:
    """在转换输出目录中寻找 Markdown，优先匹配 PDF 文件名。"""

    root = Path(output_dir)
    candidates = sorted(path for path in root.rglob("*.md") if path.is_file())
    if not candidates:
        raise FileNotFoundError(f"OpenDataLoader 未生成 Markdown 文件: {root}")
    for path in candidates:
        if path.stem == pdf_stem or path.stem.startswith(pdf_stem):
            return path
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _unique_image_key(filename: str, images: dict[str, str]) -> str:
    """生成 images/<文件名>，重复文件名自动追加序号。"""

    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", filename).strip("._")
    safe_name = safe_name or "image.bin"
    candidate = f"images/{safe_name}"
    if candidate not in images:
        return candidate
    stem, suffix = os.path.splitext(safe_name)
    index = 2
    while f"images/{stem}_{index}{suffix}" in images:
        index += 1
    return f"images/{stem}_{index}{suffix}"


def _collect_images_under_output(output_dir: str | Path) -> dict[str, str]:
    """收集 OpenDataLoader 输出目录下的图片并转为 Base64。"""

    images: dict[str, str] = {}
    for path in sorted(Path(output_dir).rglob("*")):
        if not path.is_file() or path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        key = _unique_image_key(path.name, images)
        images[key] = base64.b64encode(path.read_bytes()).decode("ascii")
    return images


def _normalize_odl_image_url(raw_url: str) -> str:
    """规范 OpenDataLoader Markdown 图片引用。"""

    value = html.unescape((raw_url or "").strip())
    value = value.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    value = value.strip().strip("<>").strip().strip('"').strip("'")
    if value.startswith("./"):
        value = value[2:]
    return value.replace("\\", "/")


def _extract_image_url(raw_url: str) -> str:
    """从 Markdown 图片 URL 中去掉可选标题。"""

    value = (raw_url or "").strip()
    if value.startswith("<") and ">" in value:
        return value[: value.find(">") + 1]
    return value.split()[0] if value else ""


def _build_image_aliases(images: dict[str, str]) -> dict[str, str]:
    """建立 basename、images/name、尖括号等引用形式到统一 key 的映射。"""

    aliases: dict[str, str] = {}
    for key in images:
        basename = os.path.basename(key)
        for alias in {
            key,
            basename,
            f"./{basename}",
            f"./{key}",
            f"<{key}>",
            f"&lt;{key}&gt;",
        }:
            aliases[_normalize_odl_image_url(alias)] = key
    return aliases


def _rewrite_markdown_image_refs(markdown: str, images: dict[str, str]) -> str:
    """把 Markdown 图片引用统一改写为 images/<文件名>。"""

    if not images:
        return markdown
    aliases = _build_image_aliases(images)

    def replace(match: re.Match[str]) -> str:
        alt_text = match.group(1)
        raw_url = _extract_image_url(match.group(2))
        url = _normalize_odl_image_url(raw_url)
        if not url or url.startswith("data:"):
            return match.group(0)
        canonical = aliases.get(url) or aliases.get(os.path.basename(url))
        if canonical is None:
            return match.group(0)
        return f"![{alt_text}]({canonical})"

    return MARKDOWN_IMAGE_RE.sub(replace, markdown)


def _run_convert(pdf_path: Path, output_dir: Path, image_dir: Path) -> None:
    """调用 opendataloader_pdf.convert() 生成 Markdown 和外置图片。"""

    module = _load_opendataloader_module()
    module.convert(
        input_path=str(pdf_path),
        output_dir=str(output_dir),
        format="markdown",
        image_output="external",
        image_dir=str(image_dir),
        quiet=True,
    )


class OpenDataLoaderParser(BaseParser):
    """使用 OpenDataLoader 解析 PDF，输出 Markdown 与外置图片。"""

    def parse_into_text(self, content: bytes) -> Document:
        """执行 OpenDataLoader 转换，失败时返回带 error metadata 的空 Document。"""

        metadata = {"parser_engine": "opendataloader"}
        file_type = (self.file_type or "").lstrip(".").lower()
        if file_type != "pdf":
            return Document(
                content="",
                metadata={**metadata, "error": f"unsupported_file_type: {file_type or 'unknown'}"},
            )
        ok, message = opendataloader_available()
        if not ok:
            return Document(
                content="",
                metadata={**metadata, "error": f"dependency_unavailable: {message}"},
            )
        try:
            text, images = self._convert_pdf(content)
        except Exception as exc:
            logger.error("OpenDataLoader 转换失败：%s", exc)
            return Document(
                content="",
                metadata={**metadata, "error": f"convert_failed: {exc}"},
            )
        if not text.strip():
            return Document(
                content="",
                images=images,
                metadata={**metadata, "error": "empty_result"},
            )
        return Document(content=text, images=images, metadata=metadata)

    def _convert_pdf(self, content: bytes) -> tuple[str, dict[str, str]]:
        """在临时目录中完成 PDF 转换并读取产物。"""

        safe_name = os.path.basename(self.file_name) or "document.pdf"
        if not safe_name.lower().endswith(".pdf"):
            safe_name = f"{Path(safe_name).stem or 'document'}.pdf"
        pdf_stem = Path(safe_name).stem
        with tempfile.TemporaryDirectory(prefix="llm-wiki-odl-") as temp_dir:
            output_dir = Path(temp_dir)
            pdf_path = output_dir / safe_name
            image_dir = output_dir / "images"
            image_dir.mkdir(parents=True, exist_ok=True)
            pdf_path.write_bytes(content)
            _run_convert(pdf_path, output_dir, image_dir)
            markdown_path = _find_markdown_file(output_dir, pdf_stem)
            text = markdown_path.read_text(encoding="utf-8", errors="replace")
            images = _collect_images_under_output(output_dir)
        return _rewrite_markdown_image_refs(text, images), images
