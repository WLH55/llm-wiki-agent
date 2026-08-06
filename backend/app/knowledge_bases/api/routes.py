"""
KB 路由：/api/v1/kb

路由层职责：参数校验 + 调 service；不写 try/except。
"""
from fastapi import APIRouter

from app.auth.api.dependencies import CurrentUserDep
from app.knowledge_bases.api.schemas import KBCreate, KBResponse
from app.knowledge_bases.service.knowledge_base import (
    build_kb_response,
    create_kb,
    get_kb,
    get_rag_config,
    get_wiki_config,
    list_kbs,
)
from app.web.dependencies import DbDep
from app.web.schemas import ApiResponse

router = APIRouter(prefix="/kb", tags=["知识库"])


async def _serialize_kb(db, kb) -> KBResponse:
    """加载 RAG/Wiki 独立配置后组装响应。"""
    rag_config = await get_rag_config(db, kb.id)
    wiki_config = await get_wiki_config(db, kb.id)
    return build_kb_response(kb, rag_config, wiki_config)


@router.post("", response_model=ApiResponse[KBResponse])
async def create_kb_endpoint(
    payload: KBCreate,
    db: DbDep,
    user: CurrentUserDep,
) -> ApiResponse[KBResponse]:
    """创建知识库"""
    kb = await create_kb(db, payload, user)
    data = await _serialize_kb(db, kb)
    return ApiResponse.success(data=data, message="创建成功")


@router.get("/{kb_id}", response_model=ApiResponse[KBResponse])
async def get_kb_endpoint(
    kb_id: int,
    db: DbDep,
    user: CurrentUserDep,
) -> ApiResponse[KBResponse]:
    """获取 KB 详情"""
    kb = await get_kb(db, kb_id, user)
    data = await _serialize_kb(db, kb)
    return ApiResponse.success(data=data)


@router.get("", response_model=ApiResponse[list[KBResponse]])
async def list_kbs_endpoint(
    db: DbDep,
    user: CurrentUserDep,
) -> ApiResponse[list[KBResponse]]:
    """列出当前租户的所有 KB"""
    kbs = await list_kbs(db, user)
    data = [await _serialize_kb(db, kb) for kb in kbs]
    return ApiResponse.success(data=data)
