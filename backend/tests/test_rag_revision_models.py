"""Revision 化 RAG 数据模型契约测试。"""

import importlib
import importlib.util

from sqlalchemy import inspect

from app.models.chunk import ContentChunk
from app.models.document import Document
from app.models.kb import KnowledgeBase


def _document_module():
    return importlib.import_module("app.models.document")


def _rag_config_module():
    spec = importlib.util.find_spec("app.models.rag_config")
    assert spec is not None, "app.models.rag_config must exist"
    return importlib.import_module("app.models.rag_config")


def test_document_has_stable_identity_and_active_revision_pointer():
    columns = {column.key for column in inspect(Document).columns}
    assert {
        "public_id",
        "source_document_key",
        "title",
        "active_revision_id",
        "version",
    } <= columns


def test_knowledge_base_owns_shared_chunking_configuration():
    columns = {column.key for column in inspect(KnowledgeBase).columns}
    assert {
        "public_id",
        "chunking_strategy",
        "chunk_size_tokens",
        "chunk_overlap_tokens",
        "chunking_options",
        "chunking_config_version",
    } <= columns


def test_document_revision_keeps_immutable_file_facts():
    module = _document_module()
    revision_type = getattr(module, "DocumentRevision", None)
    assert revision_type is not None, "DocumentRevision model must exist"
    columns = {column.key for column in inspect(revision_type).columns}
    assert {
        "document_id",
        "revision_no",
        "original_filename",
        "media_type",
        "size_bytes",
        "content_sha256",
        "storage_key",
        "parser_engine",
        "status",
        "parse_metadata",
    } <= columns


def test_candidate_chunks_are_scoped_to_revision_and_runs():
    mapper = inspect(ContentChunk)
    columns = {column.key: column for column in mapper.columns}
    assert {
        "public_id",
        "document_id",
        "revision_id",
        "processing_run_id",
        "embedding_run_id",
        "chunk_index",
        "token_count",
        "text_sha256",
        "source_locator",
    } <= columns.keys()
    assert columns["embedding_dim"].nullable


def test_rag_config_owns_embedding_and_retrieval_switches():
    module = _rag_config_module()
    config_type = getattr(module, "KnowledgeBaseRagConfig", None)
    assert config_type is not None, "KnowledgeBaseRagConfig model must exist"
    columns = {column.key for column in inspect(config_type).columns}
    assert {
        "kb_id",
        "enabled",
        "vector_enabled",
        "keyword_enabled",
        "embedding_model_key",
        "embedding_dim",
        "config_version",
    } <= columns
