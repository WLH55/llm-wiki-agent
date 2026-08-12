"""
knowledge_bases / kb_rag_configs / kb_wiki_configs 表的数据访问层

从 knowledge_base.py 迁入。
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.kb import KnowledgeBase
from app.models.kb_wiki_config import KnowledgeBaseWikiConfig
from app.models.rag_config import KnowledgeBaseRagConfig


class KnowledgeBaseRepository:
    """knowledge_bases 表的数据访问"""

    def __init__(self, db: AsyncSession):
        self.db = db


    async def create_with_configs(
        self,
        kb: KnowledgeBase,
        rag_config: KnowledgeBaseRagConfig,
        wiki_config: KnowledgeBaseWikiConfig,
    ) -> KnowledgeBase:
        """创建 KB 并写入 RAG/Wiki 配置，commit + refresh"""
        self.db.add(kb)
        await self.db.flush()
        rag_config.kb_id = kb.id
        wiki_config.kb_id = kb.id
        self.db.add(rag_config)
        self.db.add(wiki_config)
        await self.db.commit()
        await self.db.refresh(kb)
        return kb


    async def get_for_user(
        self, kb_id: int, tenant_id: int
    ) -> KnowledgeBase | None:
        """获取 KB 详情（tenant 隔离）"""
        result = await self.db.execute(
            select(KnowledgeBase)
            .where(
                KnowledgeBase.id == kb_id,
                KnowledgeBase.tenant_id == tenant_id,
                KnowledgeBase.deleted_at.is_(None),
            )
            .limit(1)
        )
        return result.scalar_one_or_none()


    async def list_for_user(self, tenant_id: int) -> list[KnowledgeBase]:
        """列出当前 tenant 的所有 KB"""
        result = await self.db.execute(
            select(KnowledgeBase)
            .where(
                KnowledgeBase.tenant_id == tenant_id,
                KnowledgeBase.deleted_at.is_(None),
            )
            .order_by(KnowledgeBase.created_at.desc())
        )
        return list(result.scalars().all())


class RagConfigRepository:
    """kb_rag_configs 表的数据访问"""

    def __init__(self, db: AsyncSession):
        self.db = db


    async def get_by_kb(self, kb_id: int) -> KnowledgeBaseRagConfig | None:
        """读取 KB 的 RAG 配置"""
        result = await self.db.execute(
            select(KnowledgeBaseRagConfig)
            .where(KnowledgeBaseRagConfig.kb_id == kb_id)
            .limit(1)
        )
        return result.scalar_one_or_none()


class WikiConfigRepository:
    """kb_wiki_configs 表的数据访问"""

    def __init__(self, db: AsyncSession):
        self.db = db


    async def get_by_kb(self, kb_id: int) -> KnowledgeBaseWikiConfig | None:
        """读取 KB 的 Wiki 配置"""
        result = await self.db.execute(
            select(KnowledgeBaseWikiConfig)
            .where(KnowledgeBaseWikiConfig.kb_id == kb_id)
            .limit(1)
        )
        return result.scalar_one_or_none()