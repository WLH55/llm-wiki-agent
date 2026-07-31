"""Outbox Publisher 进程入口契约。"""

import asyncio
import importlib
import importlib.util

import pytest


def _worker_module():
    spec = importlib.util.find_spec("app.workers.outbox_worker")
    assert spec is not None, "Outbox Publisher process entrypoint must exist"
    return importlib.import_module("app.workers.outbox_worker")


@pytest.mark.asyncio
async def test_outbox_worker_runs_publisher_with_runtime_settings(monkeypatch):
    """进程入口将运行时配置、Session 与 Taskiq sender 传给发布循环。"""
    worker = _worker_module()
    captured = {}

    async def fake_run_outbox_service(**kwargs):
        captured.update(kwargs)
        kwargs["stop"].set()

    monkeypatch.setattr(worker, "run_outbox_service", fake_run_outbox_service)
    await worker.run()

    assert captured["session_factory"] is worker.async_session_factory
    assert captured["sender"] is worker.send_task_message
    assert captured["batch_size"] == worker.settings.TASK_OUTBOX_BATCH_SIZE
    assert captured["lock_seconds"] == worker.settings.TASK_OUTBOX_LOCK_SECONDS
    assert captured["poll_seconds"] == worker.settings.TASK_OUTBOX_POLL_SECONDS
    assert isinstance(captured["stop"], asyncio.Event)
