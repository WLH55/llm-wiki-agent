"""文档解析子进程池。

parse_document 在 pebble ProcessPool 的子进程中执行：
- 超时可执行：到期 terminate 子进程（线程无法取消，进程可以）
- 崩溃隔离：解析库段错误/OOM 只损失一个子进程
- 进程级失败（超时/进程死亡）收敛为失败 ParseResult，调用方统一走
  error_code -> TerminalTaskError 映射，无需特判

约束：
- 池必须懒创建（首次使用时）。dramatiq worker 进程由 fork 产生，
  模块 import 时建池会被 fork 继承，导致池句柄损坏。
- 子进程与父进程通过 pickle 传参/传结果；raw_bytes 与 ParseResult
  均受解析预算约束，序列化开销秒级以内。
"""

import asyncio
import threading
from concurrent.futures import TimeoutError as FutureTimeoutError

from pebble import ProcessExpired, ProcessPool

from app.config import settings
from app.parsers.core.schemas import ParseErrorCode, ParseResult
from app.parsers.service.dispatch import parse_document

_pool: ProcessPool | None = None
_pool_lock = threading.Lock()


def _get_pool() -> ProcessPool:
    """懒创建进程池单例（禁止在模块 import 时创建，见模块 docstring）。"""
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = ProcessPool(max_workers=settings.PARSER_POOL_WORKERS)
    return _pool


async def parse_in_subprocess(
    filename: str,
    raw_bytes: bytes,
    engine: str,
    *,
    timeout_seconds: float | None = None,
) -> ParseResult:
    """在子进程中执行 parse_document，进程级失败收敛为 ParseResult。

    超时 -> error_code=TIMEOUT；子进程死亡 -> error_code=PARSE_FAILED。
    timeout_seconds 缺省取 settings.PARSER_TIMEOUT_SECONDS（测试可显式缩短）。
    """
    timeout = (
        timeout_seconds
        if timeout_seconds is not None
        else settings.PARSER_TIMEOUT_SECONDS
    )
    future = _get_pool().submit(parse_document, timeout, filename, raw_bytes, engine)
    try:
        return await asyncio.to_thread(future.result)
    except FutureTimeoutError:
        return ParseResult(
            engine=engine,
            error_code=ParseErrorCode.TIMEOUT,
            metadata={"error": "parser timed out and was killed"},
        )
    except ProcessExpired as exc:
        return ParseResult(
            engine=engine,
            error_code=ParseErrorCode.PARSE_FAILED,
            metadata={"error": f"parser process died: {exc}"},
        )
