"""
RQ 队列定义

提供：
- parse_queue: 文档解析队列
- enqueue_parse_document(doc_id): 入队
- run_parse_document(doc_id): 同步 wrapper（RQ 调用，内部跑 async 任务）
"""
import asyncio
import logging

from redis import Redis
from rq import Queue

from app.config import settings

logger = logging.getLogger(__name__)

_redis = Redis.from_url(settings.REDIS_URL)
parse_queue = Queue("parse", connection=_redis)


def run_parse_document(doc_id: str) -> None:
    """同步 wrapper：RQ worker 调用此函数，内部用 asyncio 跑 async 任务"""
    from app.workers.parse_document import parse_document_task

    asyncio.run(parse_document_task(doc_id))


def enqueue_parse_document(doc_id: str) -> None:
    """入队文档解析任务"""
    parse_queue.enqueue(run_parse_document, doc_id, job_timeout="10m")
    logger.info(f"文档解析任务已入队: doc_id={doc_id}")
