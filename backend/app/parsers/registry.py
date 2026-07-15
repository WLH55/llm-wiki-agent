"""ParserRegistry：注册表模式（简化版）。

替代旧 `workers/parsers.py` 的 if-elif 派发，让"加新 parser"不再需要改核心代码。

设计版本：
- 简化版（Step 5，本文件）：单 key，按 file_type 派发
- 升级版（Step 15）：双 key，按 (engine, file_type) 派发，支持同格式多引擎共存

为什么不用全局字典？
- 封装：register 时校验是否为 BaseParser 子类，挡住低级错误
- 列举能力：list_supported() 内省，消费方零硬编码
- 多实例：未来多租户场景可隔离不同 parser 集合
"""
import logging
from typing import Dict, List, Type

from app.parsers.base import BaseParser

logger = logging.getLogger(__name__)


class ParserRegistry:
    """parser 注册表（单 key 版）。

    按 file_type 派发到对应 parser 类。未知 file_type 抛 KeyError，
    由消费方决定兜底策略（如默认走 TextParser）。
    """

    def __init__(self) -> None:
        self._parsers: Dict[str, Type[BaseParser]] = {}

    def register(self, file_type: str, parser_cls: Type[BaseParser]) -> None:
        """注册 file_type → parser_cls 映射。

        - 非 BaseParser 子类：抛 TypeError（封装护栏）
        - 重复注册同一 file_type 且类不同：覆盖并打 warning（帮助发现配置冲突）
        """
        if not (isinstance(parser_cls, type) and issubclass(parser_cls, BaseParser)):
            raise TypeError(
                f"parser_cls 必须是 BaseParser 的子类，got {parser_cls!r}"
            )
        existing = self._parsers.get(file_type)
        if existing is not None and existing is not parser_cls:
            logger.warning(
                "Override existing parser for %r: %s -> %s",
                file_type,
                existing.__name__,
                parser_cls.__name__,
            )
        self._parsers[file_type] = parser_cls
        logger.info("Registered parser: %r -> %s", file_type, parser_cls.__name__)

    def get_parser_class(self, file_type: str) -> Type[BaseParser]:
        """按 file_type 取 parser 类。

        未知 file_type 抛 KeyError（消费方可 try/except 兜底为 TextParser）。
        """
        if file_type not in self._parsers:
            raise KeyError(
                f"No parser registered for file_type={file_type!r}. "
                f"Supported: {self.list_supported()}"
            )
        return self._parsers[file_type]

    def list_supported(self) -> List[str]:
        """所有已注册的 file_type（按字典序，便于测试稳定断言）。"""
        return sorted(self._parsers.keys())


# 模块级单例：项目内全局默认注册表。
# 消费方使用：`from app.parsers import registry`。
# 默认 parser 的注册见 `app/parsers/__init__.py`。
registry = ParserRegistry()
