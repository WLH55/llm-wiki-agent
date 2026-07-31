"""
Models package

import 所有 model 模块以触发 Base.metadata 注册（Alembic autogenerate 依赖）
"""
from app.models.base import Base, TenantMixin, TimestampMixin
from app.models.chunk import ContentChunk
from app.models.document import Document, DocumentRevision
from app.models.kb import KnowledgeBase
from app.models.reserved import (
    KBShare,
    LLMProvider,
    Organization,
    OrgMember,
    UserLLMKey,
    WikiFolder,
    WikiPage,
)
from app.models.source import Source
from app.models.rag_config import KnowledgeBaseRagConfig
from app.models.task_runtime import ProcessingRun, ProcessingSpan, TaskOutbox
from app.models.user import Tenant, User

__all__ = [
    "Base",
    "TenantMixin",
    "TimestampMixin",
    "Tenant",
    "User",
    "KnowledgeBase",
    "Source",
    "Document",
    "DocumentRevision",
    "KnowledgeBaseRagConfig",
    "ContentChunk",
    "ProcessingRun",
    "ProcessingSpan",
    "TaskOutbox",
    # Reserved (P2+)
    "Organization",
    "OrgMember",
    "KBShare",
    "LLMProvider",
    "UserLLMKey",
    "WikiFolder",
    "WikiPage",
]
