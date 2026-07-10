"""
Document schemas
"""
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class DocumentUploadResponse(BaseModel):
    """上传响应"""
    doc_id: uuid.UUID
    status: str
    original_filename: str


class DocumentStatusResponse(BaseModel):
    """状态响应"""
    doc_id: uuid.UUID
    status: str  # pending / processing / processed / failed
    original_filename: str
    error_message: str = ""
    processed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
