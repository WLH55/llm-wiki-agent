"""RAG 路径独立配置，不与共享分块或 Wiki 配置混放。"""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class KnowledgeBaseRagConfig(Base):
    """一个知识库最多一条 RAG 检索与 embedding 配置。"""

    __tablename__ = "kb_rag_configs"

    # KB 逻辑引用（主键）
    kb_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # 暂停或启用整个 RAG 路径；暂停不删除数据
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # 是否生成向量并启用向量召回
    vector_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # 是否建立关键词索引并启用 BM25 召回
    keyword_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # embedding adapter 使用的稳定模型标识
    embedding_model_key: Mapped[str | None] = mapped_column(String(200), default=None)
    # 模型输出维度；由模型注册信息写入，不由用户手填
    embedding_dim: Mapped[int | None] = mapped_column(Integer, default=None)
    # 配置修订号，用于并发更新和处理版本追踪
    config_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # 创建时间
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # 更新时间
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
