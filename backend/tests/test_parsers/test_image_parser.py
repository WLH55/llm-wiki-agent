"""独立图片解析器契约测试。"""

import base64
from io import BytesIO

from PIL import Image

from app.parsers import registry
from app.parsers.implementations.image import ImageParser


def _jpeg_bytes() -> bytes:
    output = BytesIO()
    exif = Image.Exif()
    exif[271] = "Learning Camera"
    Image.new("RGB", (4, 3), color="blue").save(
        output,
        format="JPEG",
        exif=exif,
    )
    return output.getvalue()


def test_image_parser_extracts_markdown_base64_and_metadata():
    content = _jpeg_bytes()
    document = ImageParser(file_name="photo.jpg").parse(content)

    assert document.content == "![photo.jpg](images/photo.jpg)"
    assert base64.b64decode(document.images["images/photo.jpg"]) == content
    assert document.metadata["format"] == "jpeg"
    assert document.metadata["width"] == 4
    assert document.metadata["height"] == 3
    assert document.metadata["mode"] == "RGB"
    assert document.metadata["exif"]["Make"] == "Learning Camera"
    assert document.metadata["ocr_status"] == "not_configured"


def test_image_parser_uses_basename_for_document_path():
    document = ImageParser(file_name="uploads/nested/photo.jpg").parse(_jpeg_bytes())
    assert "images/photo.jpg" in document.images


def test_image_parser_rejects_excessive_pixels(monkeypatch):
    import app.parsers.implementations.image as module

    monkeypatch.setattr(module, "MAX_IMAGE_PIXELS", 10)
    document = ImageParser(file_name="large.jpg").parse(_jpeg_bytes())
    assert document.content == ""
    assert "image_too_large" in document.metadata["error"]


def test_invalid_image_returns_error_metadata():
    document = ImageParser(file_name="broken.jpg").parse(b"not an image")
    assert document.content == ""
    assert document.metadata["error"].startswith("open_failed:")


def test_registry_routes_supported_images():
    for extension in ("png", "jpg", "jpeg", "gif", "webp", "bmp", "tif", "tiff"):
        assert registry.get_parser_class(extension) is ImageParser
