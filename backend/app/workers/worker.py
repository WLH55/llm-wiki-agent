"""
RQ worker 启动入口

启动：python -m app.workers.worker
"""
import logging

from redis import Redis
from rq import Worker

from app.config import settings
from app.config.logging import BeijingFormatter
from app.workers.queue import parse_queue


def main() -> None:
    """启动 RQ worker，监听 parse 队列"""
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s: %(message)s",
    )
    for handler in logging.getLogger().handlers:
        handler.setFormatter(BeijingFormatter("[%(asctime)s] %(levelname)s: %(message)s"))
    redis = Redis.from_url(settings.REDIS_URL)
    worker = Worker([parse_queue], connection=redis)
    worker.work(logging_level="INFO")


if __name__ == "__main__":
    main()
