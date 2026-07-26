"""
Document 路由：/api/v1/kb/{kb_id}/documents
"""

import uuid

from fastapi import APIRouter, File, Form, UploadFile

from app.auth.api.dependencies import CurrentUserDep
from app.config import settings
from app.parsers.api.schemas import (
    DocumentStatusResponse,
    DocumentUploadResponse,
    ParserEnginesResponse,
)
from app.parsers.service.document import (
    get_document_status,
    list_parser_engines,
    upload_document,
)
from app.web.dependencies import DbDep
from app.web.schemas import ApiResponse

router = APIRouter(prefix="/kb/{kb_id}/documents", tags=["文档"])
engines_router = APIRouter(prefix="/parsers", tags=["解析引擎"])


@router.post("", response_model=ApiResponse[DocumentUploadResponse])
async def upload_document_endpoint(
    kb_id: int,
    file: UploadFile = File(...),
    parser_engine: str = Form("builtin"),
    db: DbDep = None,  # type: ignore
    user: CurrentUserDep = None,  # type: ignore
) -> ApiResponse[DocumentUploadResponse]:
    """上传文档（自动入队异步解析）"""
    content = await file.read(settings.PARSER_MAX_FILE_BYTES + 1)
    result = await upload_document(
        db,
        kb_id,
        user,
        file.filename or "unknown",
        content,
        file.content_type or "application/octet-stream",
        parser_engine,
    )
    return ApiResponse.success(data=result, message="上传成功")


@router.get("/{doc_id}", response_model=ApiResponse[DocumentStatusResponse])
async def get_status_endpoint(
    kb_id: int,
    doc_id: uuid.UUID,
    db: DbDep = None,  # type: ignore
    user: CurrentUserDep = None,  # type: ignore
) -> ApiResponse[DocumentStatusResponse]:
    """查询文档处理状态"""
    result = await get_document_status(db, kb_id, user, doc_id)
    return ApiResponse.success(data=result)


@engines_router.get("/engines", response_model=ApiResponse[ParserEnginesResponse])
async def list_parser_engines_endpoint(
    user: CurrentUserDep = None,  # type: ignore
) -> ApiResponse[ParserEnginesResponse]:
    """返回各解析引擎可用性与可上传格式（生产白名单交集）"""
    result = list_parser_engines()
    return ApiResponse.success(data=result)
