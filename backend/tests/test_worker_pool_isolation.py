"""worker 进程 event loop 隔离契约测试。

回归背景：reaper 线程曾与 actor 的 EventLoopThread 共用同一个 async_engine，
而 asyncpg 连接绑定创建它的 event loop，跨 loop checkout 直接崩溃
（RuntimeError: Task ... got Future ... attached to a different loop）。
本测试模拟 worker 进程真实拓扑：主 loop（模拟 EventLoopThread）先用
worker 池建立连接，再启动 reaper 线程扫描，断言双方互不污染。
"""

import threading
import time

from sqlalchemy import text

from app.config import settings
from app.workers.core.database import worker_engine, worker_session_factory
from app.workers.core.reaper import run_reaper_loop


async def _worker_pool_query() -> None:
    """走 worker 私有池做一次普通查询（与 actor 用法一致）。"""
    async with worker_session_factory() as db:
        await db.execute(text("SELECT 1"))


async def test_reaper_loop_does_not_share_pool_with_worker_loop(caplog):
    caplog.set_level("ERROR", logger="app.workers.core.reaper")
    # step1: 主 loop（模拟 EventLoopThread）先用 worker 池，连接绑定到本 loop
    await _worker_pool_query()
    # Windows 开发机上 localhost 解析为 ::1 优先且 Docker 只代理 IPv4，
    # 线程内连接会挂死；钉到 127.0.0.1 保证测试只验证 loop 隔离（生产为 Linux 容器，无此问题）
    dsn = settings.POSTGRES_DSN.replace("localhost", "127.0.0.1")
    stop = threading.Event()
    thread = threading.Thread(
        target=run_reaper_loop,
        kwargs={
            "dsn": dsn,
            "interval_seconds": 0.05,
            "span_stale_seconds": 4200,
            "pending_stale_seconds": 300,
            "stop": stop,
        },
        daemon=True,
    )
    thread.start()
    try:
        # reaper 启动后立即执行第一轮扫描，留足时间跑若干轮
        time.sleep(0.5)
    finally:
        stop.set()
        thread.join(timeout=10)
    assert not thread.is_alive()
    try:
        # 断言1: reaper 扫描不允许因跨 loop 连接失败（旧实现把异常吞成这条日志）
        failures = [
            r.message for r in caplog.records if "reaper loop iteration failed" in r.message
        ]
        assert not failures, f"reaper 扫描失败: {failures}"
        # 断言2: worker 池未被 reaper 污染，主 loop 仍可正常查询
        await _worker_pool_query()
    finally:
        # 清理：关闭本次测试在池里建立的连接，避免绑定已关闭 loop 的连接残留
        await worker_engine.dispose()
