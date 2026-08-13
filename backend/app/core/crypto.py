"""
AES-256-GCM 加解密工具（models.parameters.api_key 加密存储）

密钥派生：MODEL_ENCRYPTION_KEY 环境变量，未配置时回退 JWT_SECRET；
SHA-256 派生 32 字节密钥。密文格式："v1:<nonce(12)+tag(16)+ciphertext 的 base64>"。
"""
import base64
import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# 密文前缀版本号，将来换算法时向后兼容
TOKEN_VERSION = "v1"
# nonce 长度（GCM 推荐 12 字节）
NONCE_BYTES = 12


def derive_key(secret: str) -> bytes:
    """SHA-256 派生 32 字节 AES-256 密钥。"""
    return hashlib.sha256(secret.encode("utf-8")).digest()


def encrypt_secret(plaintext: str, key: bytes) -> str:
    """加密明文，返回 "v1:<base64(nonce+tag+ciphertext)>"。"""
    nonce = os.urandom(NONCE_BYTES)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), None)
    payload = nonce + ciphertext
    return f"{TOKEN_VERSION}:{base64.b64encode(payload).decode('ascii')}"


def decrypt_secret(token: str, key: bytes) -> str:
    """解密 "v1:<base64>" 格式的密文，返回明文。"""
    version, encoded = token.split(":", 1)
    if version != TOKEN_VERSION:
        raise ValueError(f"unsupported token version: {version}")
    payload = base64.b64decode(encoded)
    nonce = payload[:NONCE_BYTES]
    ciphertext = payload[NONCE_BYTES:]
    return AESGCM(key).decrypt(nonce, ciphertext, None).decode("utf-8")
