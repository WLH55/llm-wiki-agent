"""
KB 路由：/api/v1/kb

路由层职责：参数校验 + 调 service；不写 try/except。
"""
from fastapi import APIRouter

from app.config.schemas import ApiResponse
from app.deps import CurrentUserDep, DbDep
from app.schemas.kb import KBCreate, KBResponse
from app.services.kb_service import create_kb, get_kb, list_kbs

router = APIRouter(prefix="/kb", tags=["知识库"])


@router.post("", response_model=ApiResponse[KBResponse])
async def create_kb_endpoint(
    payload: KBCreate,
    db: DbDep,
    user: CurrentUserDep,
) -> ApiResponse[KBResponse]:
    """创建知识库"""
    kb = await create_kb(db, payload, user)
    return ApiResponse.success(data=KBResponse.model_validate(kb), message="创建成功")


@router.get("/{kb_id}", response_model=ApiResponse[KBResponse])
async def get_kb_endpoint(
    kb_id: int,
    db: DbDep,
    user: CurrentUserDep,
) -> ApiResponse[KBResponse]:
    """获取 KB 详情"""
    kb = await get_kb(db, kb_id, user)
    return ApiResponse.success(data=KBResponse.model_validate(kb))


@router.get("", response_model=ApiResponse[list[KBResponse]])
async def list_kbs_endpoint(
    db: DbDep,
    user: CurrentUserDep,
) -> ApiResponse[list[KBResponse]]:
    """列出当前 tenant 的所有 KB"""
    kbs = await list_kbs(db, user)
    return ApiResponse.success(data=[KBResponse.model_validate(k) for k in kbs])
