"""
Bootstrap owner 模块

启动时（lifespan）调用 ensure_bootstrap_owner：
- 若 users 表为空 → 创建 default tenant + bootstrap owner
- 若已存在 → 跳过
"""
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security.password import hash_password
from app.config import settings
from app.models.user import Tenant, User

logger = logging.getLogger(__name__)


async def ensure_bootstrap_owner(db: AsyncSession) -> None:
    """确保 bootstrap owner 存在

    幂等：多次调用安全。
    """
    result = await db.execute(select(User).where(User.role == "owner").limit(1))
    if result.scalar_one_or_none() is not None:
        logger.info("bootstrap owner 已存在，跳过创建")
        return

    if not settings.BOOTSTRAP_OWNER_EMAIL or not settings.BOOTSTRAP_OWNER_PASSWORD:
        logger.warning(
            "BOOTSTRAP_OWNER_EMAIL 或 BOOTSTRAP_OWNER_PASSWORD 未配置，跳过 bootstrap"
        )
        return

    # 定稿 schema：tenants.owner_id NOT NULL。全库不建外键，先占位再回填：
    # 先以占位 owner_id 建 tenant，拿到 id 后建 owner 再回填。
    tenant = Tenant(name="default", owner_id=0)
    db.add(tenant)
    await db.flush()  # 拿 tenant.id

    owner = User(
        tenant_id=tenant.id,
        email=settings.BOOTSTRAP_OWNER_EMAIL,
        password_hash=hash_password(settings.BOOTSTRAP_OWNER_PASSWORD),
        role="owner",
        is_active=True,
    )
    db.add(owner)
    await db.flush()
    tenant.owner_id = owner.id
    await db.commit()

    logger.info(
        f"bootstrap owner 已创建: email={owner.email} tenant_id={tenant.id}"
    )
