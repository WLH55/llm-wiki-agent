"""文档解析模块（参考 docreader/parser/ 移植）。

公共 API：
- `Document`：parser 输出契约
- `BaseParser`：抽象基类
- `registry`：全局 parser 注册表（已注册默认 parser）

默认注册策略（Stage 2 选项 A）：
- 当前只挂 TextParser，作为 .txt / .md / 未知扩展名的统一兜底
- Stage 3 起逐步加入 MarkdownParser / PdfParser / DocxParser 等专用 parser
"""
from app.parsers.base import BaseParser
from app.parsers.document import Document
from app.parsers.registry import registry
from app.parsers.text_parser import TextParser

__all__ = ["Document", "BaseParser", "registry", "TextParser"]


def _register_defaults() -> None:
    """注册默认 parser 集合。

    Stage 2：仅 TextParser，.md / .txt / 未知扩展名统一兜底。
    后续 Stage 在此追加（如 MarkdownParser / PdfParser / DocxParser）。
    """
    registry.register("txt", TextParser)
    registry.register("md", TextParser)        # 暂时走 TextParser，Step 7 升级为 MarkdownParser
    registry.register("markdown", TextParser)  # 兼容 .markdown 扩展名


_register_defaults()
