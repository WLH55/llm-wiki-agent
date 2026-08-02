"""
Models package

import 所有 model 模块以触发 Base.metadata 注册（Alembic autogenerate 依赖）
按 2026-08-02 定稿 spec 重建后的模型注册。
"""
from app.models.base import Base, TenantMixin, TimestampMixin
from app.models.chunk import ContentChunk
from app.models.document import Document, DocumentRevision
from app.models.kb import KnowledgeBase
from app.models.kb_wiki_config import KnowledgeBaseWikiConfig
from app.models.rag_config import KnowledgeBaseRagConfig
from app.models.reserved import (
    KBShare,
    LLMProvider,
    Organization,
    OrgMember,
    UserLLMKey,
)
from app.models.search_log import SearchLog
from app.models.source import Source
from app.models.task_runtime import ProcessingRun, ProcessingSpan, TaskOutbox
from app.models.user import Tenant, User
from app.models.wiki import (
    WikiFolder,
    WikiPage,
    WikiPageDocumentRef,
    WikiPageEvidenceRef,
    WikiPageLink,
)

__all__ = [
    "Base",
    "TenantMixin",
    "TimestampMixin",
    # 基础设施
    "Tenant",
    "User",
    "Organization",
    "OrgMember",
    "KBShare",
    "LLMProvider",
    "UserLLMKey",
    # 共享根与配置
    "KnowledgeBase",
    "KnowledgeBaseRagConfig",
    "KnowledgeBaseWikiConfig",
    "Source",
    # 文档链
    "Document",
    "DocumentRevision",
    "ContentChunk",
    # Wiki
    "WikiFolder",
    "WikiPage",
    "WikiPageLink",
    "WikiPageDocumentRef",
    "WikiPageEvidenceRef",
    # 运行支撑
    "ProcessingRun",
    "ProcessingSpan",
    "TaskOutbox",
    # 检索日志
    "SearchLog",
]
