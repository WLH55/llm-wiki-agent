"""DocParser：老式 Word .doc 二进制格式解析（Stage 3 简化版）。

移植自 docreader/parser/doc_parser.py 的 antiword 命令行链路。
Stage 3 刻意不移植：
- _parse_with_docx（doc→docx 转换 + 图像抽取，依赖 libreoffice，重）
- textract（docreader 已因 SSRF 风险禁用）
- SandboxExecutor（docreader 用代理沙箱执行外部命令，本场景内网无需求）

简化策略：
1. 写 .doc 到 tempfile
2. 尝试 antiword → 失败尝试 catdoc
3. 两个都没有 → Document(content="", metadata={"error": "no_doc_tool"})

依赖外部命令：antiword 或 catdoc（apt install antiword / catdoc）。
"""
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional

from app.parsers.core.base import BaseParser
from app.parsers.core.document import Document

logger = logging.getLogger(__name__)

# 命令查找顺序：antiword 先（docreader 同款），catdoc 兜底
_DOC_TOOLS = ("antiword", "catdoc")


class DocParser(BaseParser):
    """Word .doc（老式二进制）→ Document。

    依赖外部命令：antiword 或 catdoc。两者都没装时返回空 content +
    metadata.error，由消费方决定是否报错。
    """

    def parse_into_text(self, content: bytes) -> Document:
        logger.info("Parsing DOC, content size: %d bytes", len(content))

        tool = self._find_tool()
        if not tool:
            logger.warning("No DOC tool found (antiword/catdoc) in PATH")
            return Document(
                content="",
                metadata={"error": "no_doc_tool", "tried": list(_DOC_TOOLS)},
            )

        with tempfile.NamedTemporaryFile(suffix=".doc", delete=False) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)

        try:
            text = self._run_tool(tool, tmp_path)
            logger.info("DOC parsed by %s: %d chars", tool, len(text))
            return Document(content=text, metadata={"tool": tool})
        except Exception as exc:
            logger.error("DOC parse failed with %s: %s", tool, exc)
            return Document(content="", metadata={"error": f"{tool}_failed: {exc}"})
        finally:
            try:
                tmp_path.unlink()
            except OSError:
                pass

    @staticmethod
    def _find_tool() -> Optional[str]:
        for candidate in _DOC_TOOLS:
            path = shutil.which(candidate)
            if path:
                return path
        return None

    @staticmethod
    def _run_tool(tool_path: str, file_path: Path) -> str:
        cmd: List[str] = [tool_path, str(file_path)]
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=60,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"{tool_path} exit {result.returncode}: "
                f"{result.stderr.decode('utf-8', errors='ignore')[:200]}"
            )
        return result.stdout.decode("utf-8", errors="replace")
