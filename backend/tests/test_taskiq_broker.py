"""Taskiq Redis Streams Broker 拓扑契约测试。"""

import importlib
import importlib.util

import pytest
from taskiq_redis import RedisStreamBroker

from app.workers.broker import (
    CRITICAL_QUEUE,
    DEFAULT_QUEUE,
    LOW_QUEUE,
    MULTIMODAL_QUEUE,
    WORKER_CONSUMER_GROUP,
    create_critical_broker,
    create_shared_broker,
)


def test_shared_broker_consumes_all_rag_queues():
    broker = create_shared_broker("redis://localhost:6380/15")
    assert isinstance(broker, RedisStreamBroker)
    assert broker.queue_name == DEFAULT_QUEUE
    assert broker.additional_streams == {
        CRITICAL_QUEUE: ">",
        MULTIMODAL_QUEUE: ">",
        LOW_QUEUE: ">",
    }
    assert broker.consumer_group_name == WORKER_CONSUMER_GROUP
    assert broker.consumer_id == "0-0"


def test_critical_broker_reserves_capacity_in_same_consumer_group():
    broker = create_critical_broker("redis://localhost:6380/15")
    assert isinstance(broker, RedisStreamBroker)
    assert broker.queue_name == CRITICAL_QUEUE
    assert broker.additional_streams == {}
    assert broker.consumer_group_name == WORKER_CONSUMER_GROUP
    assert broker.consumer_id == "0-0"


def _tasks_module():
    spec = importlib.util.find_spec("app.workers.tasks")
    assert spec is not None, "app.workers.tasks must exist"
    return importlib.import_module("app.workers.tasks")


def test_process_run_is_registered_on_both_worker_brokers():
    tasks = _tasks_module()
    assert tasks.shared_broker.find_task("process_run") is tasks.process_run_shared
    assert tasks.critical_broker.find_task("process_run") is tasks.process_run_critical


def test_default_run_handlers_include_revision_document_processing():
    tasks = _tasks_module()
    assert "document_process" in tasks.RUN_HANDLERS
    assert "rag_index" in tasks.RUN_HANDLERS


@pytest.mark.asyncio
async def test_taskiq_sender_routes_identity_message_to_selected_stream(monkeypatch):
    tasks = _tasks_module()
    kicked = []

    async def capture(message):
        kicked.append(message)

    monkeypatch.setattr(tasks.shared_broker, "kick", capture)
    await tasks.send_task_message("process_run", 123, "critical")
    assert len(kicked) == 1
    assert kicked[0].labels["queue_name"] == CRITICAL_QUEUE
    assert b"123" in kicked[0].message


@pytest.mark.asyncio
async def test_taskiq_sender_rejects_unknown_queue():
    tasks = _tasks_module()
    with pytest.raises(ValueError, match="unknown task queue"):
        await tasks.send_task_message("process_run", 123, "typo")
