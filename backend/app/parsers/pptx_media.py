"""PPTX 内嵌媒体提取工具。"""

import base64
import zipfile
from io import BytesIO


def extract_pptx_media(content: bytes) -> dict[str, str]:
    """提取 ``ppt/media/`` 下的文件，返回图片路径到 Base64 的映射。"""
    if not zipfile.is_zipfile(BytesIO(content)):
        raise ValueError("invalid_pptx_archive")
    images = {}
    with zipfile.ZipFile(BytesIO(content), "r") as archive:
        for name in archive.namelist():
            normalized = name.replace("\\", "/")
            if not normalized.startswith("ppt/media/") or normalized.endswith("/"):
                continue
            filename = normalized.rsplit("/", 1)[-1]
            if not filename:
                continue
            images[f"images/{filename}"] = base64.b64encode(archive.read(name)).decode()
    return images
