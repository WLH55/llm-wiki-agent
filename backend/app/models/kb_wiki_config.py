"""
kb_wiki_configs model

按 2026-08-02 定稿 spec：Wiki 路径启停和页面生成配置；一个 KB 最多一条。
全库不建外键。
"""
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class KnowledgeBaseWikiConfig(Base):
    """一个知识库最多一条 Wiki 生成配置。"""

    __tablename__ = "kb_wiki_configs"

    # KB 逻辑引用（主键）
    kb_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # 暂停或启用整个 Wiki 路径；暂停不删除页面
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # 生成模式：manual 或 on_ingest
    generation_mode: Mapped[str] = mapped_column(
        String(20), default="manual", nullable=False
    )
    # 自动生成 Wiki 页面使用的 LLM；NULL 表示使用系统默认模型
    generation_model_key: Mapped[str | None] = mapped_column(String(200), default=None)
    # 自动生成页面类型、输出语言和 prompt profile 等策略参数
    generation_options: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    # Wiki 配置修订号
    config_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # 创建时间
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # 更新时间
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
