"""解析子进程池契约测试。

回归背景：解析原来跑在 to_thread 线程里，asyncio.wait_for 超时后线程无法取消，
僵尸解析线程会耗尽线程池并拖垮 worker。子进程池（pebble）承诺三件事：
1. 超时真正可执行——到期 terminate 子进程，future 抛 TimeoutError
2. 解析崩溃（进程死亡）被隔离，收敛为异常而非拖垮调用方
3. 被杀/崩溃的 worker 会被池自动补位，池持续可用
"""

import asyncio
import time
from concurrent.futures import TimeoutError as FutureTimeoutError

import pytest
from pebble import ProcessExpired, ProcessPool

from app.parsers.core.schemas import ParseErrorCode
from app.parsers.service.parse_pool import parse_in_subprocess
from tests.fixtures.pool_targets import die_instantly, echo_ok, hang_forever


async def _result(future):
    """与生产一致的取结果方式：在默认线程池线程上同步等待。"""
    return await asyncio.to_thread(future.result)


async def test_pool_timeout_kills_and_recovers():
    """超时杀掉挂死进程，且池立即恢复可用。"""
    pool = ProcessPool(max_workers=1)
    try:
        t0 = time.monotonic()
        with pytest.raises(FutureTimeoutError):
            await _result(pool.submit(hang_forever, 2.0))
        elapsed = time.monotonic() - t0
        # 挂死目标要睡 600s；若杀不掉，这里会等满 600s 而不是 ~2s
        assert elapsed < 15, f"超时未杀掉子进程: {elapsed:.1f}s"
        # 被杀 worker 已被补位：紧接着的提交应立即成功
        assert await _result(pool.submit(echo_ok, 1.0, "alive")) == "alive"
    finally:
        pool.close()
        pool.join(timeout=10)


async def test_pool_crash_is_isolated():
    """子进程自杀（OOM/段错误等价）收敛为 ProcessExpired，不拖垮调用方。"""
    pool = ProcessPool(max_workers=1)
    try:
        with pytest.raises(ProcessExpired):
            await _result(pool.submit(die_instantly, 10.0))
        assert await _result(pool.submit(echo_ok, 1.0, "alive")) == "alive"
    finally:
        pool.close()
        pool.join(timeout=10)


async def test_parse_in_subprocess_success():
    """真实解析路径：成功返回 ParseResult（error_code 为空）。"""
    result = await parse_in_subprocess("契约测试.md", "# 标题\n\n正文".encode("utf-8"), "builtin")
    assert result.error_code is None
    assert "正文" in result.content


async def test_parse_in_subprocess_timeout_converged():
    """parse_in_subprocess 把进程级失败收敛为失败 ParseResult（不抛异常）。"""
    from app.parsers.service import parse_pool

    # 用挂死目标替换池内执行的函数，验证超时收敛逻辑
    original = parse_pool.parse_document
    parse_pool.parse_document = hang_forever
    try:
        result = await parse_pool.parse_in_subprocess(
            "挂死测试.md", b"x", "builtin", timeout_seconds=2.0
        )
    finally:
        parse_pool.parse_document = original
    assert result.error_code == ParseErrorCode.TIMEOUT
    assert result.metadata.get("error")
