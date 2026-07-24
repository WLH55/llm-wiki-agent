"""worker 的解析元数据和确定性状态写入测试。"""

import sys
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import pytest

from app.config import settings
from app.parsers.schemas import ParseErrorCode, ParseResult
from app.workers import parse_document as worker
from app.workers.parse_document import _mark_status, _metadata_for_result

DOC_ID = UUID("11111111-1111-1111-1111-111111111111")


class _SessionContext:
    def __init__(self):
        self.db = SimpleNamespace()

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, exc_type, exc, traceback):
        return False


def _install_fake_database(monkeypatch):
    context = _SessionContext()
    monkeypatch.setitem(
        sys.modules,
        "app.database",
        SimpleNamespace(async_session_factory=lambda: context),
    )
    return context.db


def _document():
    return SimpleNamespace(
        doc_id=DOC_ID,
        kb_id=7,
        minio_key="7/source.pdf",
        original_filename="source.pdf",
        parser_engine="builtin",
    )


def test_metadata_for_result_removes_free_text_error():
    result = ParseResult(
        engine="builtin",
        metadata={"format": "pdf", "error": "free text"},
        warnings=["partial_empty_pages"],
        error_code=ParseErrorCode.PARSE_FAILED,
    )
    metadata = _metadata_for_result(result)
    assert metadata == {
        "format": "pdf",
        "engine": "builtin",
        "warnings": ["partial_empty_pages"],
    }


@pytest.mark.asyncio
async def test_mark_status_failed_clears_processed_timestamp():
    db = SimpleNamespace(commit=AsyncMock())
    doc = SimpleNamespace(
        status="processed",
        error_message="",
        parse_error_code=None,
        parse_metadata={},
        processed_at=object(),
    )
    await _mark_status(
        db,
        doc,
        "failed",
        error_message="bad",
        error_code="parse_failed",
        parse_metadata={"engine": "builtin"},
    )
    assert doc.status == "failed"
    assert doc.error_message == "bad"
    assert doc.parse_error_code == "parse_failed"
    assert doc.parse_metadata == {"engine": "builtin"}
    assert doc.processed_at is None
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_mark_status_processed_clears_previous_error():
    db = SimpleNamespace(commit=AsyncMock())
    doc = SimpleNamespace(
        status="failed",
        error_message="bad",
        parse_error_code="parse_failed",
        parse_metadata={},
        processed_at=None,
    )
    await _mark_status(db, doc, "processed", parse_metadata={"warnings": []})
    assert doc.status == "processed"
    assert doc.error_message == ""
    assert doc.parse_error_code is None
    assert doc.processed_at is not None


@pytest.mark.asyncio
async def test_task_stops_before_chunking_on_parse_failure(monkeypatch):
    _install_fake_database(monkeypatch)
    doc = _document()
    mark_status = AsyncMock()
    chunk_text = Mock()
    monkeypatch.setattr(worker, "_get_doc", AsyncMock(return_value=doc))
    monkeypatch.setattr(worker, "_mark_status", mark_status)
    monkeypatch.setattr(worker, "get_bytes", lambda key: b"bad")
    monkeypatch.setattr(
        worker,
        "_parse_document",
        lambda *args: ParseResult(
            engine="builtin",
            error_code=ParseErrorCode.PARSE_FAILED,
            metadata={"error": "corrupt"},
        ),
    )
    monkeypatch.setattr(worker, "chunk_text", chunk_text)
    await worker.parse_document_task(str(DOC_ID))
    assert mark_status.await_args_list[-1].args[2] == "failed"
    assert mark_status.await_args_list[-1].kwargs["error_code"] == "parse_failed"
    chunk_text.assert_not_called()


@pytest.mark.asyncio
async def test_task_persists_images_before_chunking(monkeypatch):
    _install_fake_database(monkeypatch)
    doc = _document()
    mark_status = AsyncMock()
    chunk_text = Mock(return_value=["rewritten"])
    insert_chunks = AsyncMock()
    monkeypatch.setattr(worker, "_get_doc", AsyncMock(return_value=doc))
    monkeypatch.setattr(worker, "_mark_status", mark_status)
    monkeypatch.setattr(worker, "_insert_chunks", insert_chunks)
    monkeypatch.setattr(worker, "get_bytes", lambda key: b"pdf")
    monkeypatch.setattr(
        worker,
        "_parse_document",
        lambda *args: ParseResult(
            content="![x](images/x.png)",
            images={"images/x.png": "eA=="},
            engine="builtin",
        ),
    )
    monkeypatch.setattr(
        worker,
        "persist_parser_images",
        lambda *args: (
            "![x](minio://bucket/x.png)",
            [{"object_key": "x.png"}],
        ),
    )
    monkeypatch.setattr(worker, "chunk_text", chunk_text)
    monkeypatch.setattr(worker, "embed_texts", lambda chunks: [[0.1]])
    await worker.parse_document_task(str(DOC_ID))
    chunk_text.assert_called_once_with("![x](minio://bucket/x.png)", max_words=300, overlap=50)
    insert_chunks.assert_awaited_once()
    assert mark_status.await_args_list[-1].args[2] == "processed"
    assert mark_status.await_args_list[-1].kwargs["parse_metadata"]["images"] == [
        {"object_key": "x.png"}
    ]


@pytest.mark.asyncio
async def test_task_marks_timeout_as_failed(monkeypatch):
    _install_fake_database(monkeypatch)
    doc = _document()
    mark_status = AsyncMock()
    monkeypatch.setattr(worker, "_get_doc", AsyncMock(return_value=doc))
    monkeypatch.setattr(worker, "_mark_status", mark_status)
    monkeypatch.setattr(worker, "get_bytes", lambda key: b"pdf")
    monkeypatch.setattr(settings, "PARSER_TIMEOUT_SECONDS", 0.001)

    def slow_parse(*args):
        time.sleep(0.02)
        return ParseResult(content="late", engine="builtin")

    monkeypatch.setattr(worker, "_parse_document", slow_parse)
    await worker.parse_document_task(str(DOC_ID))
    assert mark_status.await_args_list[-1].args[2] == "failed"
    assert mark_status.await_args_list[-1].kwargs["error_code"] == "timeout"
