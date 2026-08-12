"""
sources 表的数据访问层

从 parsers/service/document.py 迁入。
"""
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.source import Source


class SourceRepository:
    """sources 表的数据访问"""

    def __init__(self, db: AsyncSession):
        self.db = db


    async def upsert_manual_source(
        self,
        tenant_id: int,
        kb_id: int,
    ) -> Source:
        """为手动上传复用同一 Source，并由数据库处理首次并发创建"""
        await self.db.execute(
            insert(Source)
            .values(
                tenant_id=tenant_id,
                kb_id=kb_id,
                source_type="manual",
                name="Manual uploads",
                config={},
                sync_cursor="",
            )
            .on_conflict_do_nothing(
                index_elements=["tenant_id", "kb_id", "source_type"],
                index_where=(Source.source_type == "manual") & Source.deleted_at.is_(None),
            )
        )
        result = await self.db.execute(
            select(Source)
            .where(
                Source.tenant_id == tenant_id,
                Source.kb_id == kb_id,
                Source.source_type == "manual",
                Source.deleted_at.is_(None),
            )
            .order_by(Source.id)
            .limit(1)
        )
        source = result.scalar_one_or_none()
        if source is None:
            raise RuntimeError("manual source missing after conflict-safe upsert")
        return source