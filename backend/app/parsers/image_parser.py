"""独立图片解析器。"""

import base64
import logging
import os
from io import BytesIO
from typing import Any

from PIL import ExifTags, Image

from app.parsers.base import BaseParser
from app.parsers.document import Document

logger = logging.getLogger(__name__)

MAX_IMAGE_PIXELS = 40_000_000


class ImageParser(BaseParser):
    """验证图片并提取尺寸、颜色模式和 EXIF 元数据。"""

    def parse_into_text(self, content: bytes) -> Document:
        """将图片 bytes 转换为 Markdown 引用和 Base64 图片映射。"""

        try:
            with Image.open(BytesIO(content)) as image:
                width, height = image.size
                if width * height > MAX_IMAGE_PIXELS:
                    raise ValueError(
                        f"image_too_large: {width}x{height} exceeds {MAX_IMAGE_PIXELS} pixels"
                    )
                image_format = (image.format or "unknown").lower()
                mode = image.mode
                exif = self._extract_exif(image)
                image.verify()
        except Exception as exc:
            logger.error("打开图片失败：%s", exc)
            return Document(
                content="",
                metadata={"format": "image", "error": f"open_failed: {exc}"},
            )

        filename = os.path.basename(self.file_name) or f"image.{image_format}"
        image_path = f"images/{filename}"
        return Document(
            content=f"![{filename}]({image_path})",
            images={image_path: base64.b64encode(content).decode("ascii")},
            metadata={
                "format": image_format,
                "width": width,
                "height": height,
                "mode": mode,
                "file_size": len(content),
                "exif": exif,
                "ocr_status": "not_configured",
            },
        )

    @staticmethod
    def _extract_exif(image: Image.Image) -> dict[str, Any]:
        """使用可读标签名提取可 JSON 序列化的 EXIF。"""

        try:
            raw_exif = image.getexif()
        except (AttributeError, OSError):
            return {}
        output: dict[str, Any] = {}
        for tag_id, value in raw_exif.items():
            tag_name = ExifTags.TAGS.get(tag_id, str(tag_id))
            if value is None or isinstance(value, (str, int, float, bool)):
                output[tag_name] = value
            else:
                output[tag_name] = str(value)
        return output
