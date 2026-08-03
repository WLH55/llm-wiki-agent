"""Taskiq Redis Streams Broker 与调度队列定义。"""

from taskiq_redis import RedisStreamBroker

from app.config import settings

QUEUE_PREFIX = "llmwiki:tasks"
CRITICAL_QUEUE = f"{QUEUE_PREFIX}:critical"
DEFAULT_QUEUE = f"{QUEUE_PREFIX}:default"
MULTIMODAL_QUEUE = f"{QUEUE_PREFIX}:multimodal"
LOW_QUEUE = f"{QUEUE_PREFIX}:low"
WORKER_CONSUMER_GROUP = "llmwiki-workers"


def _broker(
    redis_url: str,
    *,
    queue_name: str,
    additional_streams: dict[str, str] | None = None,
) -> RedisStreamBroker:
    """构造具有 ACK、Pending 恢复和首次消息回放能力的 Stream Broker。"""
    return RedisStreamBroker(
        url=redis_url,
        queue_name=queue_name,
        additional_streams=additional_streams,
        consumer_group_name=WORKER_CONSUMER_GROUP,
        consumer_id="0-0",
        idle_timeout=settings.TASK_STREAM_IDLE_TIMEOUT_MS,
        unacknowledged_lock_timeout=5,
        xread_count=settings.TASK_WORKER_CONCURRENCY,
        maxlen=None,
    )


def create_shared_broker(redis_url: str) -> RedisStreamBroker:
    """共享 lane：消费普通任务，也可吸收 critical 的突发流量。"""
    return _broker(
        redis_url,
        queue_name=DEFAULT_QUEUE,
        additional_streams={
            CRITICAL_QUEUE: ">",
            MULTIMODAL_QUEUE: ">",
            LOW_QUEUE: ">",
        },
    )


def create_critical_broker(redis_url: str) -> RedisStreamBroker:
    """保留 lane：只消费激活链路和恢复等 critical 任务。"""
    return _broker(redis_url, queue_name=CRITICAL_QUEUE)


shared_broker = create_shared_broker(settings.REDIS_URL)
critical_broker = create_critical_broker(settings.REDIS_URL)
