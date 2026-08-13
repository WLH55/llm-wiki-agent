"""
KB service：创建 / 查询 / 列表

业务编排层：不直接操作数据库，通过 KnowledgeBaseRepository / RagConfigRepository / WikiConfigRepository 访问数据。
事务边界（commit/rollback）保留在 service 层。
"""
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.service.model_bootstrap import ensure_default_models
from app.core.exceptions import ResourceNotFoundException
from app.knowledge_bases.api.schemas import KBCreate, KBResponse
from app.knowledge_bases.repository.kb_repo import (
    KnowledgeBaseRepository,
    RagConfigRepository,
    WikiConfigRepository,
)
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
    # 绑定默认 chat/embedding 模型（P1 AC8：KB 创建必须绑定模型；
    # MVP env var 模型由 ensure_default_models 幂等提供）
    chat_model_id, embedding_model_id = await ensure_default_models(db)
    kb.chat_model_id = chat_model_id
    kb.embedding_model_id = embedding_model_id
    rag_config = KnowledgeBaseRagConfig(
        vector_enabled=payload.vector_enabled,
        keyword_enabled=payload.keyword_enabled,
        embedding_model_key=payload.embedding_model,
        embedding_dim=payload.embedding_dim,
    )
    wiki_config = KnowledgeBaseWikiConfig(
        enabled=payload.wiki_enabled,
    )
    repo = KnowledgeBaseRepository(db)
    kb = await repo.create_with_configs(kb, rag_config, wiki_config)
    logger.info(f"KB 已创建: id={kb.id} name={kb.name} tenant_id={kb.tenant_id}")
    return kb


async def get_rag_config(db: AsyncSession, kb_id: int) -> KnowledgeBaseRagConfig | None:
    """读取 KB 的 RAG 配置（无则返回 None，调用方用默认值兜底）。"""
    repo = RagConfigRepository(db)
    return await repo.get_by_kb(kb_id)


async def get_wiki_config(db: AsyncSession, kb_id: int) -> KnowledgeBaseWikiConfig | None:
    """读取 KB 的 Wiki 配置（无则返回 None，调用方用默认值兜底）。"""
    repo = WikiConfigRepository(db)
    return await repo.get_by_kb(kb_id)


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
    repo = KnowledgeBaseRepository(db)
    kb = await repo.get_for_user(kb_id, user.tenant_id)
    if kb is None:
        raise ResourceNotFoundException(f"KB {kb_id} 不存在")
    return kb


async def list_kbs(db: AsyncSession, user: User) -> list[KnowledgeBase]:
    """列出当前 tenant 的所有 KB。"""
    repo = KnowledgeBaseRepository(db)
    return await repo.list_for_user(user.tenant_id)