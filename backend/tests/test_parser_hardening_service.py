"""上传产品白名单、engine 与机器可读错误载荷测试。"""

import json

import pytest
from starlette.requests import Request

from app.config import settings
from app.core.exceptions import (
    BusinessValidationException,
)
from app.parsers.schemas import ParseErrorCode
from app.parsers.service.document import validate_parser_request
from app.web.exception_handlers import validation_exception_handler


@pytest.mark.parametrize(
    "file_type",
    ["txt", "md", "markdown", "pdf", "docx", "xlsx", "csv", "pptx"],
)
def test_validate_parser_request_accepts_builtin_core_formats(file_type):
    assert validate_parser_request(f"demo.{file_type.upper()}", b"file", " BUILTIN ") == (
        file_type,
        "builtin",
    )


def test_validate_parser_request_rejects_experimental_format():
    with pytest.raises(BusinessValidationException) as exc_info:
        validate_parser_request("demo.epub", b"book", "builtin")
    assert exc_info.value.error_code == ParseErrorCode.UNSUPPORTED_TYPE.value


def test_validate_parser_request_rejects_large_file(monkeypatch):
    monkeypatch.setattr(settings, "PARSER_MAX_FILE_BYTES", 2)
    with pytest.raises(BusinessValidationException) as exc_info:
        validate_parser_request("demo.pdf", b"pdf", "builtin")
    assert exc_info.value.error_code == ParseErrorCode.TOO_LARGE.value


def test_validate_parser_request_rejects_unknown_engine():
    with pytest.raises(BusinessValidationException) as exc_info:
        validate_parser_request("demo.pdf", b"pdf", "missing")
    assert exc_info.value.error_code == ParseErrorCode.ENGINE_UNAVAILABLE.value


@pytest.mark.asyncio
async def test_validation_handler_exposes_stable_error_code():
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/upload",
            "headers": [],
            "query_string": b"",
        }
    )
    response = await validation_exception_handler(
        request,
        BusinessValidationException(
            "不支持的文件类型",
            error_code=ParseErrorCode.UNSUPPORTED_TYPE.value,
        ),
    )
    assert response.status_code == 400
    payload = json.loads(response.body)
    assert payload["data"] == {"error_code": "unsupported_type"}
