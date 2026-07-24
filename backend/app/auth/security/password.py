"""
密码哈希模块（argon2id）

使用 passlib CryptContext，argon2 是 OWASP 推荐的现代哈希算法。
"""
from passlib.context import CryptContext

_pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


def hash_password(raw: str) -> str:
    """哈希明文密码"""
    return _pwd_context.hash(raw)


def verify_password(raw: str, hashed: str) -> bool:
    """校验明文密码与哈希是否匹配"""
    return _pwd_context.verify(raw, hashed)
