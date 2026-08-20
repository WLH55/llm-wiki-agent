"""存储与资源域模型（4 张表）。"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, fk, uuid_pk


class Resource(TimestampMixin, SoftDeleteMixin, Base):
    """对象资源注册表（文件/图像）：handle 短句柄唯一，多生命周期。"""

    __tablename__ = "resources"

    id: Mapped[str] = uuid_pk()
    # 短句柄（22 字符，URL 标识，唯一）
    handle: Mapped[str] = mapped_column(String(22), nullable=False, unique=True)
    tenant_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_backend_id: Mapped[str | None] = mapped_column(String(36))
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    physical_path: Mapped[str] = mapped_column(Text, nullable=False)
    location_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # file / image 等
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="file")
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    original_name: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    size: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    # persistent / temporary
    lifecycle: Mapped[str] = mapped_column(String(16), nullable=False, default="persistent")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # active / deleted
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="active")


class ResourceBinding(Base):
    """资源与业务实体（knowledge/session/message 等）的绑定关系。"""

    __tablename__ = "resource_bindings"

    id: Mapped[str] = uuid_pk()
    resource_id: Mapped[str] = mapped_column(String(36), fk("resources.id"), nullable=False)
    tenant_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # knowledge / session / message 等
    owner_type: Mapped[str] = mapped_column(String(32), nullable=False)
    owner_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # attachment 等
    relation: Mapped[str] = mapped_column(String(32), nullable=False, default="attachment")
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ResourceAccessGrant(Base):
    """资源限时访问令牌授权（分享链接）。"""

    __tablename__ = "resource_access_grants"

    id: Mapped[str] = uuid_pk()
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    resource_id: Mapped[str] = mapped_column(String(36), fk("resources.id"), nullable=False)
    # read 等
    access_scope: Mapped[str] = mapped_column(String(16), nullable=False, default="read")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
