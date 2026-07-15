"""BaseParser：所有 parser 的抽象基类。

设计模式：
- 抽象基类（abc.ABC）：阻止直接实例化
- 抽象方法（@abstractmethod）：强制子类实现 parse_into_text
- 模板方法（parse）：基类写日志流程，子类填具体解析逻辑
"""
import logging
import os
from abc import ABC, abstractmethod
from typing import Optional

from app.parsers.document import Document

logger = logging.getLogger(__name__)


class BaseParser(ABC):
    """所有 parser 的抽象基类。

    子类必须实现 parse_into_text。parse() 是模板方法，统一处理日志。
    """

    def __init__(
        self,
        file_name: str = "",
        file_type: Optional[str] = None,
        **kwargs,
    ):
        self.file_name = file_name
        # 如果没显式传 file_type，从 file_name 扩展名推断
        self.file_type = file_type or os.path.splitext(file_name)[1].lstrip(".")
        logger.info("Init parser: file=%s, type=%s", file_name, self.file_type)

    @abstractmethod
    def parse_into_text(self, content: bytes) -> Document:
        """子类必须实现：bytes → Document 的实际解析逻辑。"""

    def parse(self, content: bytes) -> Document:
        """模板方法：日志前置 + 调子类 parse_into_text + 日志后置。

        消费方应该调 parse() 而非 parse_into_text()，保证日志统一。
        """
        logger.info(
            "Parsing with %s, bytes=%d", self.__class__.__name__, len(content)
        )
        document = self.parse_into_text(content)
        logger.info(
            "Extracted %d chars from %s",
            len(document.content),
            self.file_name or "(unknown)",
        )
        return document
