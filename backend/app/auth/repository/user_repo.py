"""
users / tenants 表的数据访问层

从 auth/service/auth.py / bootstrap.py 迁入。
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import Tenant, User


class UserRepository:
    """users 表的数据访问"""

    def __init__(self, db: AsyncSession):
        self.db = db


    async def get_by_email(self, email: str) -> User | None:
        """按邮箱加载用户"""
        result = await self.db.execute(
            select(User).where(User.email == email).limit(1)
        )
        return result.scalar_one_or_none()


    async def exists_owner(self) -> bool:
        """检查是否已存在 owner 角色用户"""
        result = await self.db.scalar(
            select(User).where(User.role == "owner").limit(1)
        )
        return result is not None


class TenantRepository:
    """tenants 表的数据访问"""

    def __init__(self, db: AsyncSession):
        self.db = db


    async def create_with_owner(
        self,
        tenant: Tenant,
        owner: User,
    ) -> tuple[Tenant, User]:
        """创建 tenant + owner 并回填 owner_id，commit"""
        self.db.add(tenant)
        await self.db.flush()
        owner.tenant_id = tenant.id
        self.db.add(owner)
        await self.db.flush()
        tenant.owner_id = owner.id
        await self.db.commit()
        return tenant, owner