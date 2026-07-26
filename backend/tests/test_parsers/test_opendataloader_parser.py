"""OpenDataLoader 高级解析器契约测试。"""

import base64
from pathlib import Path
from types import SimpleNamespace

import app.parsers.implementations.opendataloader as module
from app.parsers.implementations.opendataloader import (
    OpenDataLoaderParser,
    _collect_images_under_output,
    _find_markdown_file,
    _normalize_odl_image_url,
    _rewrite_markdown_image_refs,
)


def test_opendataloader_available_accepts_java_17_and_package(monkeypatch):
    monkeypatch.setattr(module.shutil, "which", lambda name: "java")
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            stdout="",
            stderr='openjdk version "17.0.9"',
        ),
    )
    monkeypatch.setattr(module, "_load_opendataloader_module", lambda: object())

    ok, message = module.opendataloader_available()

    assert ok is True
    assert message == ""


def test_opendataloader_available_rejects_old_java(monkeypatch):
    monkeypatch.setattr(module.shutil, "which", lambda name: "java")
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            stdout="",
            stderr='java version "1.8.0_381"',
        ),
    )

    ok, message = module.opendataloader_available()

    assert ok is False
    assert "java_too_old" in message


def test_opendataloader_available_reports_missing_package(monkeypatch):
    monkeypatch.setattr(module.shutil, "which", lambda name: "java")
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            stdout="",
            stderr='openjdk version "17.0.9"',
        ),
    )

    def missing_package():
        raise ImportError("missing opendataloader")

    monkeypatch.setattr(module, "_load_opendataloader_module", missing_package)

    ok, message = module.opendataloader_available()

    assert ok is False
    assert "opendataloader-pdf 未安装" in message


def test_find_markdown_prefers_pdf_stem(tmp_path):
    other = tmp_path / "other.md"
    target = tmp_path / "paper.md"
    other.write_text("other", encoding="utf-8")
    target.write_text("# Paper", encoding="utf-8")

    assert _find_markdown_file(tmp_path, "paper") == target


def test_collect_images_and_rewrite_markdown_refs(tmp_path):
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    image_path = image_dir / "fig1.png"
    image_path.write_bytes(b"png")

    images = _collect_images_under_output(tmp_path)
    markdown = "见 ![图](<images/fig1.png>) 和 ![同图](./fig1.png)。"
    rewritten = _rewrite_markdown_image_refs(markdown, images)

    assert images["images/fig1.png"] == base64.b64encode(b"png").decode("ascii")
    assert "![图](images/fig1.png)" in rewritten
    assert "![同图](images/fig1.png)" in rewritten
    assert _normalize_odl_image_url("&lt;images/fig1.png&gt;") == "images/fig1.png"


def test_rewrite_skips_data_uri_images():
    markdown = "![inline](data:image/png;base64,abc)"
    assert _rewrite_markdown_image_refs(markdown, {"images/a.png": "abc"}) == markdown


def test_opendataloader_parser_reads_markdown_images_and_cleans_temp(monkeypatch):
    captured: dict[str, str] = {}

    class FakeOpenDataLoader:
        def convert(self, **kwargs):
            output_dir = Path(kwargs["output_dir"])
            image_dir = Path(kwargs["image_dir"])
            captured["output_dir"] = str(output_dir)
            image_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "doc.md").write_text(
                "# Hello\n\n![pic](<images/pic.png>)",
                encoding="utf-8",
            )
            (image_dir / "pic.png").write_bytes(b"png")

    monkeypatch.setattr(module, "opendataloader_available", lambda: (True, ""))
    monkeypatch.setattr(module, "_load_opendataloader_module", lambda: FakeOpenDataLoader())

    document = OpenDataLoaderParser(file_name="doc.pdf").parse(b"%PDF")

    assert "# Hello" in document.content
    assert "![pic](images/pic.png)" in document.content
    assert document.images["images/pic.png"] == base64.b64encode(b"png").decode("ascii")
    assert document.metadata["parser_engine"] == "opendataloader"
    assert not Path(captured["output_dir"]).exists()


def test_opendataloader_parser_rejects_non_pdf():
    document = OpenDataLoaderParser(file_name="doc.docx").parse(b"doc")

    assert document.content == ""
    assert document.metadata["error"].startswith("unsupported_file_type:")


def test_opendataloader_parser_returns_error_on_convert_failure(monkeypatch):
    def broken_convert(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(module, "opendataloader_available", lambda: (True, ""))
    monkeypatch.setattr(module, "_run_convert", broken_convert)

    document = OpenDataLoaderParser(file_name="doc.pdf").parse(b"%PDF")

    assert document.content == ""
    assert document.metadata["error"].startswith("convert_failed:")
