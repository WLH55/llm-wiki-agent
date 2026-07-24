"""解析图片持久化的路径、限额与正文替换测试。"""

import base64
from uuid import UUID

import pytest

from app.parsers.errors import ParserAssetError
from app.parsers.schemas import ParseErrorCode
from app.parsers.service.asset import persist_parser_images

DOC_ID = UUID("11111111-1111-1111-1111-111111111111")


def test_persist_images_uses_safe_content_addressed_key(monkeypatch):
    uploaded = []

    def fake_upload(key, data, content_type):
        uploaded.append((key, data, content_type))
        return f"bucket/{key}"

    monkeypatch.setattr("app.parsers.service.asset.upload_bytes", fake_upload)
    encoded = base64.b64encode(b"image-bytes").decode("ascii")
    content, metadata = persist_parser_images(
        7,
        DOC_ID,
        "![封面](../../secret.png)",
        {"../../secret.png": encoded},
        100,
    )
    object_key = metadata[0]["object_key"]
    assert object_key.startswith(f"7/{DOC_ID}/images/")
    assert ".." not in object_key
    assert object_key.endswith("-secret.png")
    assert uploaded == [(object_key, b"image-bytes", "image/png")]
    assert metadata[0]["size_bytes"] == len(b"image-bytes")
    assert metadata[0]["uri"] in content
    assert "base64" not in str(metadata)


def test_persist_images_rejects_invalid_base64(monkeypatch):
    monkeypatch.setattr(
        "app.parsers.service.asset.upload_bytes",
        lambda *args, **kwargs: None,
    )
    with pytest.raises(ParserAssetError) as exc_info:
        persist_parser_images(7, DOC_ID, "", {"x.png": "%%%"}, 100)
    assert exc_info.value.error_code is ParseErrorCode.PARSE_FAILED


def test_persist_images_enforces_total_limit(monkeypatch):
    uploaded = []
    monkeypatch.setattr(
        "app.parsers.service.asset.upload_bytes",
        lambda *args, **kwargs: uploaded.append(args),
    )
    encoded = base64.b64encode(b"123").decode("ascii")
    with pytest.raises(ParserAssetError) as exc_info:
        persist_parser_images(7, DOC_ID, "", {"a.png": encoded}, 2)
    assert exc_info.value.error_code is ParseErrorCode.TOO_LARGE
    assert uploaded == []


def test_persist_images_maps_upload_failure(monkeypatch):
    def fail_upload(*args, **kwargs):
        raise OSError("storage offline")

    monkeypatch.setattr("app.parsers.service.asset.upload_bytes", fail_upload)
    encoded = base64.b64encode(b"123").decode("ascii")
    with pytest.raises(ParserAssetError) as exc_info:
        persist_parser_images(7, DOC_ID, "", {"a.png": encoded}, 100)
    assert exc_info.value.error_code is ParseErrorCode.PARSE_FAILED
    assert str(exc_info.value) == "image_upload_failed: a.png"
