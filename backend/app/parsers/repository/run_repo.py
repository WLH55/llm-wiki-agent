"""
processing_runs 表的数据访问层

从 parsers/service/document.py 迁入。
processing_runs 的创建/状态管理由 workers 层（task_runtime）负责，
这里只抽取 document.py 中直接查询 processing_runs 的 SELECT 操作。
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task_runtime import ProcessingRun


class ProcessingRunRepository:
    """processing_runs 表的数据访问（查询用）"""

    def __init__(self, db: AsyncSession):
        self.db = db


    async def latest_for_revision(
        self, revision_id: int
    ) -> ProcessingRun | None:
        """查询某 revision 最新的 processing_run（按 id 降序）"""
        result = await self.db.execute(
            select(ProcessingRun)
            .where(
                ProcessingRun.scope_type == "revision",
                ProcessingRun.scope_id == revision_id,
            )
            .order_by(ProcessingRun.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()