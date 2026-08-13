"""
KnowledgeBase model

按 2026-08-02 定稿 spec 重建：删除 embedding_model / embedding_dim /
vector_enabled / keyword_enabled / wiki_enabled / graph_enabled（这些归属
kb_rag_configs / kb_wiki_configs，见 spec 决策#3）；description 改 TEXT。
本表只保留身份、归属、通用描述和唯一的共享分块策略。
"""
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin, TimestampMixin


class KnowledgeBase(Base, TimestampMixin, TenantMixin):
    """知识库（RAG/Wiki 共享聚合根）"""
    __tablename__ = "knowledge_bases"

    # 内部关联 ID
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # API、日志和导出使用的稳定公开 ID，全局唯一
    public_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), default=uuid4, nullable=False, unique=True
    )
    # 用户可见的 KB 名称
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # KB 通用说明
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)

    # RAG 与 Wiki 共用同一套切块事实，具体下游不得各自覆盖。
    # 共享分块算法标识：recursive_tokens / markdown_heading / fixed_tokens / parent_child
    chunking_strategy: Mapped[str] = mapped_column(
        String(50), default="recursive_tokens", nullable=False
    )
    # 单个共享 chunk 的目标 token 上限
    chunk_size_tokens: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    # 相邻共享 chunk 重复保留的 token 数
    chunk_overlap_tokens: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    # 当前分块策略的专属扩展参数，按策略 JSON Schema 校验
    chunking_options: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    # 共享分块配置修订号，用于并发更新与重建追踪
    chunking_config_version: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False
    )

    # 模型绑定（004 migration，ADR-0020 工作区级模型配置）
    # MVP 必填由 API 层保证；历史行可为 NULL
    embedding_model_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )
    chat_model_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )
