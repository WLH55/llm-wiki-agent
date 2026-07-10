"""
Search 路由：GET /api/v1/kb/{kb_id}/search
"""
from fastapi import APIRouter, Query

from app.config.exceptions import BusinessValidationException
from app.config.schemas import ApiResponse
from app.deps import CurrentUserDep, DbDep
from app.schemas.search import SearchResponse
from app.services.search_service import search as search_service

router = APIRouter(prefix="/kb/{kb_id}/search", tags=["检索"])


@router.get("", response_model=ApiResponse[SearchResponse])
async def search_endpoint(
    kb_id: int,
    q: str = Query(..., min_length=1, max_length=500, description="查询字符串"),
    mode: str = Query("rag", pattern="^(rag|wiki)$", description="检索模式"),
    limit: int = Query(10, ge=1, le=50, description="返回 top-K 数量"),
    db: DbDep = None,  # type: ignore
    user: CurrentUserDep = None,  # type: ignore
) -> ApiResponse[SearchResponse]:
    """RAG 检索（向量 + BM25 + RRF 融合）"""
    try:
        hits = await search_service(
            db, kb_id, user.tenant_id, q, mode=mode, limit=limit
        )
    except NotImplementedError as e:
        raise BusinessValidationException(str(e))

    return ApiResponse.success(
        data=SearchResponse(
            query=q,
            kb_id=kb_id,
            mode=mode,
            total=len(hits),
            hits=hits,
        )
    )
