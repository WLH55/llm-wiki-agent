"""
models 表的数据访问层

从 chat/service/model_bootstrap.py 迁入（模块改名 agent + repository 分层）。
职责：models 表的 CRUD + 跨表数据访问（KB -> 模型绑定链）；
加密/环境变量判断等业务规则留在 service 层。
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessValidationException, ResourceNotFoundException
from app.knowledge_bases.repository.kb_repo import KnowledgeBaseRepository
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


    async def get_by_id(self, model_id: int) -> Model | None:
        """按 id 加载未删除模型行，无则 None。"""
        result = await self.db.execute(
            select(Model).where(
                Model.id == model_id,
                Model.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()


    async def get_chat_parameters(self, kb_id: int) -> tuple[str, dict]:
        """跨表数据访问：KB 绑定的 chat 模型的 (name, parameters 原始配置)。

        数据访问收敛在此：查 KB -> 判空/判绑定 -> 查模型 -> 判空。
        返回的 parameters 里 api_key 仍是密文，解密是 service 层业务规则。
        """
        kb = await KnowledgeBaseRepository(self.db).get_by_id(kb_id)
        if kb is None:
            raise ResourceNotFoundException(f"知识库 {kb_id} 不存在")
        if kb.chat_model_id is None:
            raise BusinessValidationException(f"知识库 {kb_id} 未绑定 chat 模型")
        model = await self.get_by_id(kb.chat_model_id)
        if model is None:
            raise ResourceNotFoundException(f"chat 模型 {kb.chat_model_id} 不存在")
        return model.name, model.parameters


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
