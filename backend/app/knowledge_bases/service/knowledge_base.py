"""
KB service：创建 / 查询 / 列表

按 2026-08-02 定稿 schema：
- knowledge_bases 只保存身份/归属/共享分块策略；
- RAG 开关与 embedding 配置写入 kb_rag_configs；
- Wiki 启停写入 kb_wiki_configs；
- API 响应保持旧字段名（embedding_model 等），由 service 从配置表组装。
"""
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ResourceNotFoundException
from app.knowledge_bases.api.schemas import KBCreate, KBResponse
from app.models.kb import KnowledgeBase
from app.models.kb_wiki_config import KnowledgeBaseWikiConfig
from app.models.rag_config import KnowledgeBaseRagConfig
from app.models.user import User

logger = logging.getLogger(__name__)

_DEFAULT_EMBEDDING_MODEL = "BAAI/bge-m3"
_DEFAULT_EMBEDDING_DIM = 1024


async def create_kb(db: AsyncSession, payload: KBCreate, user: User) -> KnowledgeBase:
    """创建 KB（绑定当前 user 的 tenant_id），并写入 RAG/Wiki 独立配置。"""
    kb = KnowledgeBase(
        tenant_id=user.tenant_id,
        name=payload.name,
        description=payload.description,
    )
    db.add(kb)
    await db.flush()

    db.add(
        KnowledgeBaseRagConfig(
            kb_id=kb.id,
            vector_enabled=payload.vector_enabled,
            keyword_enabled=payload.keyword_enabled,
            embedding_model_key=payload.embedding_model,
            embedding_dim=payload.embedding_dim,
        )
    )
    db.add(
        KnowledgeBaseWikiConfig(
            kb_id=kb.id,
            enabled=payload.wiki_enabled,
        )
    )
    await db.commit()
    await db.refresh(kb)
    logger.info(f"KB 已创建: id={kb.id} name={kb.name} tenant_id={kb.tenant_id}")
    return kb


async def get_rag_config(db: AsyncSession, kb_id: int) -> KnowledgeBaseRagConfig | None:
    """读取 KB 的 RAG 配置（无则返回 None，调用方用默认值兜底）。"""
    result = await db.execute(
        select(KnowledgeBaseRagConfig)
        .where(KnowledgeBaseRagConfig.kb_id == kb_id)
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_wiki_config(db: AsyncSession, kb_id: int) -> KnowledgeBaseWikiConfig | None:
    """读取 KB 的 Wiki 配置（无则返回 None，调用方用默认值兜底）。"""
    result = await db.execute(
        select(KnowledgeBaseWikiConfig)
        .where(KnowledgeBaseWikiConfig.kb_id == kb_id)
        .limit(1)
    )
    return result.scalar_one_or_none()


def build_kb_response(
    kb: KnowledgeBase,
    rag_config: KnowledgeBaseRagConfig | None,
    wiki_config: KnowledgeBaseWikiConfig | None,
) -> KBResponse:
    """把 KB 与独立配置组装成 API 响应（字段名兼容旧前端）。"""
    return KBResponse(
        id=kb.id,
        name=kb.name,
        description=kb.description,
        tenant_id=kb.tenant_id,
        embedding_model=(
            rag_config.embedding_model_key
            if rag_config and rag_config.embedding_model_key
            else _DEFAULT_EMBEDDING_MODEL
        ),
        embedding_dim=(
            rag_config.embedding_dim
            if rag_config and rag_config.embedding_dim
            else _DEFAULT_EMBEDDING_DIM
        ),
        vector_enabled=rag_config.vector_enabled if rag_config else True,
        keyword_enabled=rag_config.keyword_enabled if rag_config else True,
        wiki_enabled=wiki_config.enabled if wiki_config else True,
        graph_enabled=False,  # MVP 未实现图谱路径，响应保留旧字段占位
    )


async def get_kb(db: AsyncSession, kb_id: int, user: User) -> KnowledgeBase:
    """获取 KB 详情（tenant 隔离）。"""
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
    """列出当前 tenant 的所有 KB。"""
    result = await db.execute(
        select(KnowledgeBase)
        .where(
            KnowledgeBase.tenant_id == user.tenant_id,
            KnowledgeBase.deleted_at.is_(None),
        )
        .order_by(KnowledgeBase.created_at.desc())
    )
    return list(result.scalars().all())
