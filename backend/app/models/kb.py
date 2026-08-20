"""知识库 / 文档 / 切块 / 向量域模型（9 张表）。

注意：embedding 列（halfvec）只在迁移 DDL 中定义，ORM 不映射向量本体，
向量写入/检索走 chunk_repo 风格的 raw SQL（CAST(:embedding AS halfvec)）。
"""
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, uuid_pk


class VectorStore(TimestampMixin, SoftDeleteMixin, Base):
    """外部向量库注册（pgvector/elasticsearch/milvus 等），知识库可选绑定。"""

    __tablename__ = "vector_stores"

    id: Mapped[str] = uuid_pk()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    engine_type: Mapped[str] = mapped_column(String(50), nullable=False)
    connection_config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    index_config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # 0 = 系统级
    tenant_id: Mapped[int] = mapped_column(BigInteger, nullable=False)


class StorageBackend(TimestampMixin, SoftDeleteMixin, Base):
    """统一存储后端注册（local/minio/cos），供文档与资源使用。"""

    __tablename__ = "storage_backends"

    id: Mapped[str] = uuid_pk()
    tenant_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # 来源：user / system
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="user")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    legacy_alias: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class KnowledgeBase(TimestampMixin, SoftDeleteMixin, Base):
    """知识库容器：继承租户级模型/存储配置，可覆盖；type 区分 document/faq。"""

    __tablename__ = "knowledge_bases"

    id: Mapped[str] = uuid_pk()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding_model_id: Mapped[str] = mapped_column(String(64), nullable=False)
    summary_model_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # COS 对象存储配置（历史字段）
    cos_config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # VLM（视觉大模型）配置
    vlm_config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    extract_config: Mapped[dict | None] = mapped_column(JSONB)
    # 是否临时知识库（UI 隐藏）
    is_temporary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # document / faq / hybrid
    type: Mapped[str] = mapped_column(String(32), nullable=False, default="document")
    faq_config: Mapped[dict | None] = mapped_column(JSONB)
    question_generation_config: Mapped[dict | None] = mapped_column(JSONB)
    # 存储提供方配置（仅 provider 名；凭据来自租户级配置）
    storage_provider_config: Mapped[dict | None] = mapped_column(JSONB)
    is_pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    pinned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # ASR 配置：{"enabled","model_id","language"}
    asr_config: Mapped[dict | None] = mapped_column(JSONB)
    # 关联 vector_stores.id；NULL = 租户默认（env 派生）
    vector_store_id: Mapped[str | None] = mapped_column(String(36))
    # {"auto_ingest","synthesis_model_id","wiki_language","max_pages_per_ingest"}
    wiki_config: Mapped[dict | None] = mapped_column(JSONB)
    # {"vector_enabled","keyword_enabled","wiki_enabled","graph_enabled"}
    indexing_strategy: Mapped[dict | None] = mapped_column(JSONB)
    creator_id: Mapped[str | None] = mapped_column(String(36))
    storage_backend_id: Mapped[str | None] = mapped_column(String(36))


class KnowledgeTag(TimestampMixin, SoftDeleteMixin, Base):
    """知识库内标签，用于 FAQ 分类与过滤。"""

    __tablename__ = "knowledge_tags"

    # WeKnora 原 PK 无默认值；应用侧显式生成
    id: Mapped[str] = uuid_pk()
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    knowledge_base_id: Mapped[str] = mapped_column(String(36), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    color: Mapped[str | None] = mapped_column(String(32))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 对外 API 自增 ID
    seq_id: Mapped[int | None] = mapped_column(BigInteger)


class Knowledge(TimestampMixin, SoftDeleteMixin, Base):
    """知识条目：文档/FAQ；parse_status 生命周期 unprocessed→processing→finalizing→completed。"""

    __tablename__ = "knowledges"

    id: Mapped[str] = uuid_pk()
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    knowledge_base_id: Mapped[str] = mapped_column(String(36), nullable=False)
    # document / faq / chat_history 等
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # 来源（URL/路径/内容）
    source: Mapped[str] = mapped_column(String(2048), nullable=False)
    # unprocessed/processing/finalizing/completed/failed
    parse_status: Mapped[str] = mapped_column(String(50), nullable=False, default="unprocessed")
    # enabled/disabled
    enable_status: Mapped[str] = mapped_column(String(50), nullable=False, default="enabled")
    # 覆盖知识库级配置的 Embedding 模型
    embedding_model_id: Mapped[str | None] = mapped_column(String(64))
    file_name: Mapped[str | None] = mapped_column(String(255))
    file_type: Mapped[str | None] = mapped_column(String(50))
    file_size: Mapped[int | None] = mapped_column(BigInteger)
    file_path: Mapped[str | None] = mapped_column(Text)
    file_hash: Mapped[str | None] = mapped_column(String(64))
    storage_size: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
    # none/summarizing/completed/failed
    summary_status: Mapped[str | None] = mapped_column(String(32), default="none")
    last_faq_import_result: Mapped[dict | None] = mapped_column(JSONB)
    # 来源渠道：web/api/browser_extension/wechat 等
    channel: Mapped[str] = mapped_column(String(50), nullable=False, default="web")
    # 未完成的富化子任务数（parse_status=finalizing 时 >0）
    pending_subtasks_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    custom_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class Chunk(TimestampMixin, SoftDeleteMixin, Base):
    """知识切块（text/table/image/faq），支持父子层级与前后链；可编辑并留修订。"""

    __tablename__ = "chunks"

    id: Mapped[str] = uuid_pk()
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    knowledge_base_id: Mapped[str] = mapped_column(String(36), nullable=False)
    knowledge_id: Mapped[str] = mapped_column(String(36), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    start_at: Mapped[int] = mapped_column(Integer, nullable=False)
    end_at: Mapped[int] = mapped_column(Integer, nullable=False)
    pre_chunk_id: Mapped[str | None] = mapped_column(String(36))
    next_chunk_id: Mapped[str | None] = mapped_column(String(36))
    # text/table/image/faq
    chunk_type: Mapped[str] = mapped_column(String(20), nullable=False, default="text")
    parent_chunk_id: Mapped[str | None] = mapped_column(String(36))
    image_info: Mapped[str | None] = mapped_column(Text)
    relation_chunks: Mapped[dict | None] = mapped_column(JSONB)
    indirect_relation_chunks: Mapped[dict | None] = mapped_column(JSONB)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB)
    # 标签 ID（knowledge_tags.id，弃用中）
    tag_id: Mapped[str | None] = mapped_column(String(36))
    # 块处理状态（0 正常）
    status: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    # 位标志（bit1=推荐等，默认 1）
    flags: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # 对外 API 使用的自增 ID
    seq_id: Mapped[int | None] = mapped_column(BigInteger)
    # {"url","frame_count","has_vlm_analysis","has_asr",...}
    video_info: Mapped[str | None] = mapped_column(Text)
    # 原始内容（未编辑的源文本）
    source_content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # 内容修订号（编辑历史）
    content_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # ready/pending/failed
    index_status: Mapped[str] = mapped_column(String(16), nullable=False, default="ready")
    last_editor_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    # 上下文标题（编辑时保留的标题）
    context_header: Mapped[str] = mapped_column(Text, nullable=False, default="")


class ChunkRevision(Base):
    """块编辑修订历史（chunk 手动编辑后回溯）。"""

    __tablename__ = "chunk_revisions"

    id: Mapped[str] = uuid_pk()
    tenant_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    knowledge_base_id: Mapped[str] = mapped_column(String(36), nullable=False)
    knowledge_id: Mapped[str] = mapped_column(String(36), nullable=False)
    chunk_id: Mapped[str] = mapped_column(String(36), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    editor_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    # user 等
    edit_source: Mapped[str] = mapped_column(String(16), nullable=False, default="user")
    edited_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Embedding(TimestampMixin, Base):
    """向量索引核心表：source 唯一，halfvec 向量（DDL 侧），content 供 BM25 检索。"""

    __tablename__ = "embeddings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 来源 ID（chunk/knowledge id）
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # 来源类型枚举（chunk 等）
    source_type: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_id: Mapped[str | None] = mapped_column(String(64))
    knowledge_id: Mapped[str | None] = mapped_column(String(64))
    knowledge_base_id: Mapped[str | None] = mapped_column(String(64))
    # 文本内容（BM25 检索用）
    content: Mapped[str | None] = mapped_column(Text)
    dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    # 向量本体（halfvec）不映射；读写走 raw SQL
    is_enabled: Mapped[bool | None] = mapped_column(Boolean, default=True)
    # 标签 ID（FAQ 优先级过滤）
    tag_id: Mapped[str | None] = mapped_column(String(36))


class KnowledgeTagRelation(Base):
    """知识条目-标签多对多关系表。"""

    __tablename__ = "knowledge_tag_relations"

    knowledge_id: Mapped[str] = mapped_column(
        String(36), primary_key=True
    )
    tag_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class TemporaryDocument(TimestampMixin, SoftDeleteMixin, Base):
    """会话中暂存的上传文档（uploaded/processing/ready/failed/expired，过期清理）。"""

    __tablename__ = "temporary_documents"

    id: Mapped[str] = uuid_pk()
    tenant_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False)
    resource_ref: Mapped[str] = mapped_column(Text, nullable=False)
    file_name: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_type: Mapped[str] = mapped_column(String(32), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # uploaded/processing/ready/failed/expired
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="uploaded")
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    chunks: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    image_refs: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    processing_options: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
