"""按解析引擎和文件格式分发 parser 的注册表。"""

from collections.abc import Callable

from app.parsers.core.base import BaseParser

BUILTIN_ENGINE = "builtin"


class ParserEngineRegistry:
    """维护 ``engine -> file_type -> parser`` 的双 key 映射。"""

    def __init__(self) -> None:
        self._engines: dict[str, dict[str, type[BaseParser]]] = {}
        self._descriptions: dict[str, str] = {}
        self._check_available: dict[str, Callable[[], tuple[bool, str]]] = {}
        self._unavailable_hints: dict[str, str] = {}

    @staticmethod
    def _normalize_engine(engine: str) -> str:
        """规范化引擎名。"""
        return engine.strip().lower()

    @staticmethod
    def _normalize_file_type(file_type: str) -> str:
        """规范化文件扩展名。"""
        return file_type.strip().lower().lstrip(".")

    def register(
        self,
        engine: str,
        file_types: dict[str, type[BaseParser]],
        description: str = "",
        check_available: Callable[[], tuple[bool, str]] | None = None,
        unavailable_hint: str = "",
    ) -> None:
        """校验整张格式映射后，原子替换指定引擎。"""
        normalized_engine = self._normalize_engine(engine)
        if not normalized_engine:
            raise ValueError("engine 规范化后不能为空")
        normalized_mapping: dict[str, type[BaseParser]] = {}
        for file_type, parser_cls in file_types.items():
            normalized_file_type = self._normalize_file_type(file_type)
            if not normalized_file_type:
                raise ValueError("file_type 规范化后不能为空")
            if normalized_file_type in normalized_mapping:
                raise ValueError(f"file_type 规范化后重复: {normalized_file_type!r}")
            if not (isinstance(parser_cls, type) and issubclass(parser_cls, BaseParser)):
                raise TypeError(
                    f"parser 必须是 BaseParser 的子类，got {parser_cls!r} "
                    f"for file_type={file_type!r}"
                )
            normalized_mapping[normalized_file_type] = parser_cls
        self._engines[normalized_engine] = normalized_mapping
        self._descriptions[normalized_engine] = description
        self._unavailable_hints[normalized_engine] = unavailable_hint
        if check_available is None:
            self._check_available.pop(normalized_engine, None)
        else:
            self._check_available[normalized_engine] = check_available

    def get_parser_class(self, engine: str, file_type: str) -> type[BaseParser]:
        """返回指定引擎与格式对应的 parser；找不到则抛 KeyError。"""
        requested_engine = self._normalize_engine(engine)
        normalized_file_type = self._normalize_file_type(file_type)
        requested_mapping = self._engines.get(requested_engine, {})
        parser_cls = requested_mapping.get(normalized_file_type)
        if parser_cls is not None:
            return parser_cls
        raise KeyError(
            f"No parser registered for engine={requested_engine!r}, "
            f"file_type={normalized_file_type!r}. "
            f"Supported: {self.list_supported(requested_engine)}"
        )

    def list_supported(self, engine: str = BUILTIN_ENGINE) -> list[str]:
        """返回指定引擎支持的格式，未知引擎返回空列表。"""
        normalized_engine = self._normalize_engine(engine)
        return sorted(self._engines.get(normalized_engine, {}))

    def list_engines(self) -> list[dict[str, object]]:
        """返回所有引擎及其运行时可用状态。"""
        return [self.get_engine_status(engine) for engine in self.get_engine_names()]

    def get_engine_status(self, engine: str) -> dict[str, object] | None:
        """返回单个引擎状态；未知引擎返回 None。"""
        normalized_engine = self._normalize_engine(engine)
        if normalized_engine not in self._engines:
            return None
        available = True
        unavailable_reason = ""
        probe = (
            None
            if normalized_engine == BUILTIN_ENGINE
            else self._check_available.get(normalized_engine)
        )
        if probe is not None:
            try:
                probe_result = probe()
                if not (
                    isinstance(probe_result, tuple)
                    and len(probe_result) == 2
                    and type(probe_result[0]) is bool
                    and isinstance(probe_result[1], str)
                ):
                    available = False
                    unavailable_reason = "可用性检查返回值无效"
                else:
                    available, unavailable_reason = probe_result
            except Exception as exc:
                available = False
                unavailable_reason = f"可用性检查失败: {exc}"
        if available:
            unavailable_reason = ""
        else:
            hint = self._unavailable_hints.get(normalized_engine, "").strip()
            reason_parts = [part for part in (unavailable_reason.strip(), hint) if part]
            unavailable_reason = "；".join(reason_parts)
        return {
            "name": normalized_engine,
            "description": self._descriptions.get(normalized_engine, ""),
            "file_types": self.list_supported(normalized_engine),
            "available": available,
            "unavailable_reason": unavailable_reason,
        }

    def get_engine_names(self) -> list[str]:
        """返回稳定排序的引擎名称。"""
        return sorted(self._engines)


# 项目内共享的默认注册表，具体映射在 app.parsers 初始化时注册。
registry = ParserEngineRegistry()
