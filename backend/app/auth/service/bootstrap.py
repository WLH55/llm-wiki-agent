"""
Bootstrap owner 模块

启动时（lifespan）调用 ensure_bootstrap_owner：
- 若 users 表为空 → 创建 default tenant + bootstrap owner
- 若已存在 → 跳过

业务编排层：通过 UserRepository / TenantRepository 访问数据。
"""
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.repository.user_repo import TenantRepository, UserRepository
from app.auth.security.password import hash_password
from app.config import settings
from app.models.user import Tenant, User

logger = logging.getLogger(__name__)


async def ensure_bootstrap_owner(db: AsyncSession) -> None:
    """确保 bootstrap owner 存在

    幂等：多次调用安全。
    """
    user_repo = UserRepository(db)
    if await user_repo.exists_owner():
        logger.info("bootstrap owner 已存在，跳过创建")
        return

    if not settings.BOOTSTRAP_OWNER_EMAIL or not settings.BOOTSTRAP_OWNER_PASSWORD:
        logger.warning(
            "BOOTSTRAP_OWNER_EMAIL 或 BOOTSTRAP_OWNER_PASSWORD 未配置，跳过 bootstrap"
        )
        return

    # 定稿 schema：tenants.owner_id NOT NULL。全库不建外键，先占位再回填：
    # repository 层负责创建 tenant + owner + 回填 owner_id + commit
    tenant = Tenant(name="default", owner_id=0)
    owner = User(
        email=settings.BOOTSTRAP_OWNER_EMAIL,
        password_hash=hash_password(settings.BOOTSTRAP_OWNER_PASSWORD),
        role="owner",
        is_active=True,
    )
    tenant_repo = TenantRepository(db)
    tenant, owner = await tenant_repo.create_with_owner(tenant, owner)

    logger.info(
        f"bootstrap owner 已创建: email={owner.email} tenant_id={tenant.id}"
    )