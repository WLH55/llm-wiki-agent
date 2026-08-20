"""
Models package

import 所有 model 模块以触发 Base.metadata 注册（Alembic autogenerate 依赖）。
2026-08-20 起全量采用 WeKnora 53 张表结构（docs/adr/0001-adopt-weknora-schema.md），
模型按域分文件；索引/约束以 alembic/versions/001_weknora_baseline.py 的 DDL 为权威。
"""
from app.models.agent import (
    CustomAgent,
    McpOauthClient,
    McpOauthToken,
    McpService,
    McpToolApproval,
    WebSearchProvider,
)
from app.models.base import Base, SoftDeleteMixin, TimestampMixin
from app.models.chat import (
    Message,
    MessageSuggestionEvent,
    MessageSuggestionSet,
    Session,
)
from app.models.datasource import DataSource, SyncLog
from app.models.identity import (
    AuditLog,
    AuthToken,
    SystemSetting,
    Tenant,
    TenantApiKey,
    TenantInvitation,
    TenantMember,
    User,
)
from app.models.im import EmbedChannel, ImChannel, ImChannelSession
from app.models.kb import (
    Chunk,
    ChunkRevision,
    Embedding,
    Knowledge,
    KnowledgeBase,
    KnowledgeTag,
    KnowledgeTagRelation,
    StorageBackend,
    TemporaryDocument,
    VectorStore,
)
from app.models.model_conf import Model
from app.models.org import (
    AgentShare,
    KbShare,
    Organization,
    OrganizationJoinRequest,
    OrganizationMember,
    OrganizationTenantMember,
    TenantDisabledSharedAgent,
)
from app.models.personal import UserKbPin, UserResourceFavorite
from app.models.storage import Resource, ResourceAccessGrant, ResourceBinding
from app.models.task import (
    KnowledgeProcessingSpan,
    TaskDeadLetter,
    TaskPendingOp,
)
from app.models.wiki import (
    WikiFolder,
    WikiPage,
    WikiPageIssue,
    WikiPageRevision,
)

__all__ = [
    "Base",
    "TimestampMixin",
    "SoftDeleteMixin",
    # 租户 / 用户 / 认证 / 权限（8）
    "Tenant",
    "User",
    "AuthToken",
    "TenantMember",
    "TenantInvitation",
    "TenantApiKey",
    "SystemSetting",
    "AuditLog",
    # 模型配置（1）
    "Model",
    # 知识库 / 文档 / 切块 / 向量 / 存储后端（10，storage_backends 归本域）
    "KnowledgeBase",
    "Knowledge",
    "Chunk",
    "ChunkRevision",
    "Embedding",
    "KnowledgeTag",
    "KnowledgeTagRelation",
    "TemporaryDocument",
    "VectorStore",
    "StorageBackend",
    # 会话 / 消息（4）
    "Session",
    "Message",
    "MessageSuggestionSet",
    "MessageSuggestionEvent",
    # Agent / MCP / Web 搜索（6）
    "CustomAgent",
    "McpService",
    "McpToolApproval",
    "McpOauthClient",
    "McpOauthToken",
    "WebSearchProvider",
    # IM / 嵌入渠道（3）
    "ImChannel",
    "ImChannelSession",
    "EmbedChannel",
    # 组织协作 / 分享（7）
    "Organization",
    "OrganizationMember",
    "OrganizationTenantMember",
    "OrganizationJoinRequest",
    "KbShare",
    "AgentShare",
    "TenantDisabledSharedAgent",
    # Wiki（4）
    "WikiFolder",
    "WikiPage",
    "WikiPageIssue",
    "WikiPageRevision",
    # 数据源（2）
    "DataSource",
    "SyncLog",
    # 存储与资源（3）
    "Resource",
    "ResourceBinding",
    "ResourceAccessGrant",
    # 任务队列 / 处理追踪（3）
    "TaskPendingOp",
    "TaskDeadLetter",
    "KnowledgeProcessingSpan",
    # 用户个性化（2）
    "UserResourceFavorite",
    "UserKbPin",
]
