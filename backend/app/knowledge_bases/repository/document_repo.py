"""
documents / document_revisions 表的数据访问层

从 rag_ingestion.py / parsers/service/document.py 迁入。
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentRevision


class DocumentRepository:
    """documents 表的数据访问"""

    def __init__(self, db: AsyncSession):
        self.db = db


    async def get_by_id(self, document_id: int) -> Document | None:
        """按 id 加载文档"""
        return await self.db.get(Document, document_id)


    async def get_by_public_id(
        self, public_id: str, kb_id: int, tenant_id: int
    ) -> Document | None:
        """按 public_id（tenant 隔离）加载文档"""
        result = await self.db.execute(
            select(Document)
            .where(
                Document.public_id == public_id,
                Document.kb_id == kb_id,
                Document.tenant_id == tenant_id,
                Document.deleted_at.is_(None),
            )
            .limit(1)
        )
        return result.scalar_one_or_none()


    async def create_document(self, document: Document) -> Document:
        """创建文档，flush 获取 id"""
        self.db.add(document)
        await self.db.flush()
        return document


class DocumentRevisionRepository:
    """document_revisions 表的数据访问"""

    def __init__(self, db: AsyncSession):
        self.db = db


    async def get_by_id(self, revision_id: int) -> DocumentRevision | None:
        """按 id 加载文档版本"""
        return await self.db.get(DocumentRevision, revision_id)


    async def create_revision(self, revision: DocumentRevision) -> DocumentRevision:
        """创建文档版本，flush 获取 id"""
        self.db.add(revision)
        await self.db.flush()
        return revision


    async def list_by_document(
        self, document_id: int
    ) -> list[DocumentRevision]:
        """列出文档的所有版本（按 revision_no 降序）"""
        result = await self.db.execute(
            select(DocumentRevision)
            .where(
                DocumentRevision.document_id == document_id,
                DocumentRevision.deleted_at.is_(None),
            )
            .order_by(DocumentRevision.revision_no.desc())
        )
        return list(result.scalars().all())