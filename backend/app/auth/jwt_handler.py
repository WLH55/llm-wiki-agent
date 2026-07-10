"""
JWT 模块（HS256，无 refresh token）

参 ADR-0008 §MVP 鉴权极简：
- HS256（对称加密，单一服务够用）
- 24h 过期（env 可配）
- 无 refresh token（过期重登）
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt

from app.config import settings


def create_access_token(user_id: int) -> str:
    """生成 access token"""
    now = datetime.now(timezone.utc)
    expire = now + timedelta(hours=settings.JWT_EXPIRE_HOURS)
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """解码 token，失败抛 JWTError"""
    payload: dict = jwt.decode(
        token,
        settings.JWT_SECRET,
        algorithms=[settings.JWT_ALGORITHM],
    )
    return payload


def get_user_id_from_token(token: str) -> Optional[int]:
    """便捷方法：从 token 提取 user_id，失败返回 None"""
    try:
        payload = decode_token(token)
        sub = payload.get("sub")
        return int(sub) if sub else None
    except (JWTError, ValueError, TypeError):
        return None
