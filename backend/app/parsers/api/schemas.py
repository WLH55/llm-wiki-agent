"""
Document schemas
"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DocumentUploadResponse(BaseModel):
    """上传响应"""

    doc_id: uuid.UUID
    status: str
    original_filename: str
    parser_engine: str = "builtin"


class DocumentStatusResponse(BaseModel):
    """状态响应"""

    doc_id: uuid.UUID
    status: str  # pending / processing / processed / failed
    original_filename: str
    error_message: str = ""
    error_code: str | None = None
    parser_engine: str = "builtin"
    parse_metadata: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    processed_at: datetime | None = None

    model_config = {"from_attributes": True}


class ParserEngineInfo(BaseModel):
    """单个解析引擎的能力与可用性。"""

    name: str
    description: str = ""
    available: bool = True
    unavailable_reason: str = ""
    file_types: list[str] = Field(default_factory=list)


class ParserEnginesResponse(BaseModel):
    """全站解析引擎能力清单。"""

    uploadable_file_types: list[str] = Field(default_factory=list)
    engines: list[ParserEngineInfo] = Field(default_factory=list)
