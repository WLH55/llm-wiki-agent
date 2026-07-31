"""Outbox Publisher 与失联 Run 补偿循环。"""

import asyncio
import logging
import random
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.workers.outbox import claim_outbox_batch
from app.workers.publisher import TaskSender, publish_outbox_claim
from app.workers.reaper import recover_stalled_runs

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PublishBatchResult:
    """单轮 Outbox 批处理计数。"""

    claimed: int
    published: int
    failed: int


def _default_jitter(delay: float) -> float:
    return random.uniform(0, delay * 0.2) if delay > 0 else 0


async def publish_outbox_batch(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    sender: TaskSender,
    batch_size: int,
    lock_seconds: float,
    retry_base_seconds: float,
    retry_max_seconds: float,
    retry_jitter=_default_jitter,
) -> PublishBatchResult:
    """抢占并发布一批 Outbox；每条消息独立确认或释放。"""
    async with session_factory() as db:
        async with db.begin():
            claims = await claim_outbox_batch(
                db,
                batch_size=batch_size,
                lock_seconds=lock_seconds,
            )

    published = 0
    for claim in claims:
        raw_delay = min(
            retry_max_seconds,
            retry_base_seconds * (2**claim.publish_attempts),
        )
        retry_delay = max(0.0, raw_delay + retry_jitter(raw_delay))
        async with session_factory() as db:
            async with db.begin():
                success = await publish_outbox_claim(
                    db,
                    claim,
                    sender=sender,
                    retry_delay_seconds=retry_delay,
                )
        published += int(success)
    return PublishBatchResult(
        claimed=len(claims),
        published=published,
        failed=len(claims) - published,
    )


async def run_reaper_batch(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    batch_size: int,
    stale_after_seconds: float,
) -> list[int]:
    """在一个短事务内补偿一批长期 pending 或租约过期 Run。"""
    async with session_factory() as db:
        async with db.begin():
            return await recover_stalled_runs(
                db,
                batch_size=batch_size,
                stale_after_seconds=stale_after_seconds,
            )


async def run_outbox_service(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    sender: TaskSender,
    stop: asyncio.Event,
    batch_size: int,
    lock_seconds: float,
    poll_seconds: float,
    retry_base_seconds: float,
    retry_max_seconds: float,
    reaper_interval_seconds: float,
    stale_after_seconds: float,
) -> None:
    """持续发布 Outbox，并周期性补偿可能失联的 Run。"""
    loop = asyncio.get_running_loop()
    next_reaper_at = loop.time()
    while not stop.is_set():
        try:
            result = await publish_outbox_batch(
                session_factory=session_factory,
                sender=sender,
                batch_size=batch_size,
                lock_seconds=lock_seconds,
                retry_base_seconds=retry_base_seconds,
                retry_max_seconds=retry_max_seconds,
            )
            if loop.time() >= next_reaper_at:
                recovered = await run_reaper_batch(
                    session_factory=session_factory,
                    batch_size=batch_size,
                    stale_after_seconds=stale_after_seconds,
                )
                if recovered:
                    logger.warning("Reaper 已补投失联 Run: run_ids=%s", recovered)
                next_reaper_at = loop.time() + reaper_interval_seconds
            if result.claimed:
                continue
        except Exception:
            logger.exception("Outbox Publisher 批处理失败，将继续重试")

        try:
            await asyncio.wait_for(stop.wait(), timeout=poll_seconds)
        except TimeoutError:
            pass
