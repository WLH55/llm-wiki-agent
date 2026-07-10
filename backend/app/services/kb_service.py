"""
KB service：创建 / 查询 / 列表

Service 层职责：业务逻辑 + try/except + 业务异常抛出。
"""
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.exceptions import BusinessValidationException, ResourceNotFoundException
from app.models.kb import KnowledgeBase
from app.models.user import User
from app.schemas.kb import KBCreate

logger = logging.getLogger(__name__)


async def create_kb(db: AsyncSession, payload: KBCreate, user: User) -> KnowledgeBase:
    """创建 KB（绑定当前 user 的 tenant_id）"""
    kb = KnowledgeBase(
        tenant_id=user.tenant_id,
        name=payload.name,
        description=payload.description,
        embedding_model=payload.embedding_model,
        embedding_dim=payload.embedding_dim,
        vector_enabled=payload.vector_enabled,
        keyword_enabled=payload.keyword_enabled,
        wiki_enabled=payload.wiki_enabled,
        graph_enabled=payload.graph_enabled,
    )
    db.add(kb)
    await db.commit()
    await db.refresh(kb)
    logger.info(f"KB 已创建: id={kb.id} name={kb.name} tenant_id={kb.tenant_id}")
    return kb


async def get_kb(db: AsyncSession, kb_id: int, user: User) -> KnowledgeBase:
    """获取 KB 详情（tenant 隔离）"""
    result = await db.execute(
        select(KnowledgeBase)
        .where(
            KnowledgeBase.id == kb_id,
            KnowledgeBase.tenant_id == user.tenant_id,
            KnowledgeBase.deleted_at.is_(None),
        )
        .limit(1)
    )
    kb = result.scalar_one_or_none()
    if kb is None:
        raise ResourceNotFoundException(f"KB {kb_id} 不存在")
    return kb


async def list_kbs(db: AsyncSession, user: User) -> list[KnowledgeBase]:
    """列出当前 tenant 的所有 KB"""
    result = await db.execute(
        select(KnowledgeBase)
        .where(
            KnowledgeBase.tenant_id == user.tenant_id,
            KnowledgeBase.deleted_at.is_(None),
        )
        .order_by(KnowledgeBase.created_at.desc())
    )
    return list(result.scalars().all())
