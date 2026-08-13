"""
models 表的数据访问层

从 chat/service/model_bootstrap.py 迁入（模块改名 agent + repository 分层）。
职责：models 表的 CRUD；加密/环境变量判断等业务规则留在 service 层。
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.model import Model


class ModelRepository:
    """models 表（工作区级模型配置）的数据访问"""

    def __init__(self, db: AsyncSession):
        self.db = db


    async def find_id(
        self,
        tenant_id: int,
        model_type: str,
        name: str,
    ) -> int | None:
        """按 (tenant_id, model_type, name) 查未删除模型的 id，无则 None。"""
        result = await self.db.execute(
            select(Model.id).where(
                Model.tenant_id == tenant_id,
                Model.model_type == model_type,
                Model.name == name,
                Model.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()


    async def create(
        self,
        tenant_id: int,
        name: str,
        model_type: str,
        source: str,
        parameters: dict,
    ) -> int:
        """插入模型配置行，flush 后返回 model id。"""
        model = Model(
            tenant_id=tenant_id,
            name=name,
            model_type=model_type,
            source=source,
            parameters=parameters,
        )
        self.db.add(model)
        await self.db.flush()
        return model.id
