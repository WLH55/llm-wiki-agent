"""上传产品白名单、engine 与机器可读错误载荷测试。"""

import json

import pytest
from starlette.requests import Request

from app.config import settings
from app.core.exceptions import (
    BusinessValidationException,
)
from app.parsers.core.registry import BUILTIN_ENGINE
from app.parsers.core.schemas import ParseErrorCode
from app.parsers.service.document import (
    PRODUCTION_FILE_TYPES,
    list_parser_engines,
    validate_parser_request,
)
from app.web.exception_handlers import validation_exception_handler


@pytest.mark.parametrize(
    "file_type",
    [
        "txt",
        "md",
        "markdown",
        "pdf",
        "docx",
        "doc",
        "xlsx",
        "xls",
        "csv",
        "pptx",
        "html",
        "htm",
        "mhtml",
        "mht",
        "epub",
        "png",
        "jpg",
        "jpeg",
        "gif",
        "webp",
        "bmp",
        "tif",
        "tiff",
    ],
)
def test_validate_parser_request_accepts_builtin_core_formats(file_type):
    assert validate_parser_request(f"demo.{file_type.upper()}", b"file", " BUILTIN ") == (
        file_type,
        "builtin",
    )


def test_validate_parser_request_rejects_unsupported_format():
    with pytest.raises(BusinessValidationException) as exc_info:
        validate_parser_request("demo.xyz", b"book", "builtin")
    assert exc_info.value.error_code == ParseErrorCode.UNSUPPORTED_TYPE.value


def test_validate_parser_request_rejects_large_file(monkeypatch):
    monkeypatch.setattr(settings, "PARSER_MAX_FILE_BYTES", 2)
    with pytest.raises(BusinessValidationException) as exc_info:
        validate_parser_request("demo.pdf", b"pdf", "builtin")
    assert exc_info.value.error_code == ParseErrorCode.TOO_LARGE.value
    assert str(exc_info.value) == "文件过大: 0.00 MB（最大 0.00 MB）"


def test_validate_parser_request_rejects_unknown_engine():
    with pytest.raises(BusinessValidationException) as exc_info:
        validate_parser_request("demo.pdf", b"pdf", "missing")
    assert exc_info.value.error_code == ParseErrorCode.ENGINE_UNAVAILABLE.value


def test_list_parser_engines_uploadable_matches_production_whitelist():
    result = list_parser_engines()
    assert result.uploadable_file_types == sorted(PRODUCTION_FILE_TYPES)


def test_list_parser_engines_file_types_subset_of_whitelist():
    result = list_parser_engines()
    for engine in result.engines:
        assert set(engine.file_types) <= PRODUCTION_FILE_TYPES


def test_list_parser_engines_includes_available_builtin():
    result = list_parser_engines()
    names = {engine.name: engine for engine in result.engines}
    assert BUILTIN_ENGINE in names
    assert names[BUILTIN_ENGINE].available is True
    assert names[BUILTIN_ENGINE].unavailable_reason == ""


def test_list_parser_engines_markitdown_excludes_ppt():
    result = list_parser_engines()
    names = {engine.name: engine for engine in result.engines}
    markitdown = names.get("markitdown")
    if markitdown is not None:
        assert "ppt" not in markitdown.file_types


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
