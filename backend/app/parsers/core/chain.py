"""责任链与管道组合 parser。

FirstParser：依次尝试多个 parser，返回第一个 is_valid 的结果。
PipelineParser：前一个 parser 的 content 作为后一个 parser 的输入，并合并 images/metadata。
"""
import logging
from typing import Dict, List, Tuple, Type

from app.parsers.core.base import BaseParser
from app.parsers.core.document import Document
from app.parsers.utils import encoding

logger = logging.getLogger(__name__)


class FirstParser(BaseParser):
    """首个成功即返回的责任链 parser。"""

    _parser_cls: Tuple[Type["BaseParser"], ...] = ()

    def __init__(self, *args, **kwargs):
        """实例化配置好的 parser 类列表。"""
        super().__init__(*args, **kwargs)
        self._parsers: List[BaseParser] = []
        for parser_cls in self._parser_cls:
            self._parsers.append(parser_cls(*args, **kwargs))

    def parse_into_text(self, content: bytes) -> Document:
        """依次尝试 parser，返回第一个有效 Document。"""
        for parser in self._parsers:
            logger.info("FirstParser: using parser %s", parser.__class__.__name__)
            try:
                document = parser.parse_into_text(content)
            except Exception:
                logger.exception(
                    "FirstParser: parser %s raised exception; trying next parser",
                    parser.__class__.__name__,
                )
                continue
            if document.is_valid():
                logger.info(
                    "FirstParser: parser %s succeeded", parser.__class__.__name__
                )
                return document
        return Document()

    @classmethod
    def create(cls, *parser_classes: Type["BaseParser"]) -> Type["FirstParser"]:
        """动态生成绑定了 parser 序列的 FirstParser 子类。"""
        names = "_".join(parser.__name__ for parser in parser_classes)
        return type(f"FirstParser_{names}", (cls,), {"_parser_cls": parser_classes})


class PipelineParser(BaseParser):
    """管道 parser：A 的输出喂给 B，并累积 images/metadata。"""

    _parser_cls: Tuple[Type["BaseParser"], ...] = ()

    def __init__(self, *args, **kwargs):
        """实例化配置好的 parser 类列表。"""
        super().__init__(*args, **kwargs)
        self._parsers: List[BaseParser] = []
        for parser_cls in self._parser_cls:
            self._parsers.append(parser_cls(*args, **kwargs))

    def parse_into_text(self, content: bytes) -> Document:
        """按顺序执行管道，并把各阶段 images/metadata 合并到最终 Document。"""
        images: Dict[str, str] = {}
        metadata: Dict = {}
        document = Document()
        for parser in self._parsers:
            logger.info("PipelineParser: using parser %s", parser.__class__.__name__)
            document = parser.parse_into_text(content)
            content = encoding.encode_bytes(document.content)
            images.update(document.images)
            metadata.update(document.metadata)
        document.images.update(images)
        document.metadata.update(metadata)
        return document

    @classmethod
    def create(cls, *parser_classes: Type["BaseParser"]) -> Type["PipelineParser"]:
        """动态生成绑定了 parser 序列的 PipelineParser 子类。"""
        names = "_".join(parser.__name__ for parser in parser_classes)
        return type(f"PipelineParser_{names}", (cls,), {"_parser_cls": parser_classes})
