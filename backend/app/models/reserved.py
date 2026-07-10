"""
P2+ 才用的预留表（MVP 创建空表，避免后续 ALTER 大表锁表）

参 ADR-0008 §MVP schema 预留但不实现

注意：WikiPage 在这里定义，被 ContentChunk.wiki_page_id 外键引用
"""
from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Organization(Base, TimestampMixin):
    """组织（P2 才用）"""
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)


class OrgMember(Base, TimestampMixin):
    """组织成员（P2 才用）"""
    __tablename__ = "org_members"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(50), default="member", nullable=False)


class KBShare(Base, TimestampMixin):
    """KB 共享（P2 才用）"""
    __tablename__ = "kb_shares"

    id: Mapped[int] = mapped_column(primary_key=True)
    kb_id: Mapped[int] = mapped_column(nullable=False, index=True)
    org_id: Mapped[int] = mapped_column(nullable=False, index=True)
    permission: Mapped[str] = mapped_column(String(50), default="read", nullable=False)


class LLMProvider(Base, TimestampMixin):
    """LLM 服务商配置（P2 BYOK 才用）"""
    __tablename__ = "llm_providers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    api_base: Mapped[str] = mapped_column(String(500), default="", nullable=False)


class UserLLMKey(Base, TimestampMixin):
    """用户 LLM Key（P2 BYOK 才用）"""
    __tablename__ = "user_llm_keys"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(nullable=False, index=True)
    provider_id: Mapped[int] = mapped_column(nullable=False, index=True)
    encrypted_key: Mapped[str] = mapped_column(String(1000), nullable=False)


class WikiFolder(Base, TimestampMixin):
    """wiki 目录树（P2 才用，参 ADR-0003）"""
    __tablename__ = "wiki_folders"

    id: Mapped[int] = mapped_column(primary_key=True)
    kb_id: Mapped[int] = mapped_column(nullable=False, index=True)
    parent_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    materialized_path: Mapped[str] = mapped_column(String(1000), default="/", nullable=False)


class WikiPage(Base, TimestampMixin):
    """wiki 页面（第二批 LLM 抽取后才用）

    page_type: entity / concept / synthesis
    """
    __tablename__ = "wiki_pages"

    id: Mapped[int] = mapped_column(primary_key=True)
    kb_id: Mapped[int] = mapped_column(nullable=False, index=True)
    folder_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)
    page_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
