"""
Model（工作区级模型配置）ORM

照搬 WeKnora 设计（ADR-0020）：
- 模型归属 tenant，admin 统一配置，KB 通过 embedding_model_id / chat_model_id 引用
- parameters JSONB 承载厂商配置，api_key 用 AES-256-GCM 加密（见 app/core/crypto.py）
- MVP 由 env var 初始化 1 个 chat + 1 个 embedding 模型（启动时写入，见
  app/chat/service/model_bootstrap.py）
"""
from sqlalchemy import BigInteger, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

# 模型类型常量
MODEL_TYPE_CHAT = "chat"
MODEL_TYPE_EMBEDDING = "embedding"
# 协议来源常量（OpenAI 兼容协议）
MODEL_SOURCE_OPENAI = "openai"


class Model(Base, TimestampMixin):
    """工作区级模型配置（一个 tenant 内共享）"""

    __tablename__ = "models"

    # 内部关联 ID
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # 租户逻辑引用
    tenant_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    # 用户可见的配置名，如 deepseek-v4-flash / jina-embeddings-v5-text-small
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # chat | embedding（P3 加 rerank）
    model_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # 协议来源：openai（OpenAI 兼容协议）
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    # 模型描述
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # 厂商配置：{"base_url": "...", "api_key": "v1:...（AES-256-GCM 加密）",
    #           "model_name": "...", "timeout_seconds": 120}
    parameters: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
