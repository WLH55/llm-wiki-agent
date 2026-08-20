"""模型配置域模型（1 张表）。"""
from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDeleteMixin, TimestampMixin


class Model(TimestampMixin, SoftDeleteMixin, Base):
    """模型注册中心：type 决定用途（KnowledgeQA/Embedding/Rerank 等），tenant_id=0 为系统内置。"""

    __tablename__ = "models"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    # 模型类型：KnowledgeQA / Embedding / Rerank / ASR / VLM 等
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    # 模型来源：OpenAI / Ollama / 自定义 等
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # 模型参数（base_url、api_key 等）
    parameters: Mapped[dict] = mapped_column(JSONB, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 托管方标识（yaml 等）
    managed_by: Mapped[str] = mapped_column(String(32), nullable=False, default="")
