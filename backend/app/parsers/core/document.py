"""Document：所有 parser 的统一输出契约。

裁剪自 docreader/models/routes.py：去掉 chunks 字段（分块独立在 workers/chunker.py）。
"""
from typing import Any, Dict

from pydantic import BaseModel, Field


class Document(BaseModel):
    """parser 输出。

    content: 解析后的文本（markdown 字符串）
    images: 图片路径 → base64 字符串（含图文档才有）
    metadata: 元数据（标题/作者/页数/...）
    """

    content: str = Field(default="", description="解析后的 markdown 文本")
    images: Dict[str, str] = Field(default_factory=dict, description="图片路径 → base64")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="文档元数据")

    def is_valid(self) -> bool:
        """parser 是否解出了实际内容（ChainParser 的 FirstParser 用它判断要不要试下一个）。"""
        return self.content != ""
