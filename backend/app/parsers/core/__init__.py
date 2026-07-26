"""Parser 核心抽象。"""

from app.parsers.core.base import BaseParser
from app.parsers.core.chain import FirstParser, PipelineParser
from app.parsers.core.document import Document
from app.parsers.core.registry import BUILTIN_ENGINE, ParserEngineRegistry, registry

__all__ = [
    "BaseParser",
    "FirstParser",
    "PipelineParser",
    "Document",
    "BUILTIN_ENGINE",
    "ParserEngineRegistry",
    "registry",
]
