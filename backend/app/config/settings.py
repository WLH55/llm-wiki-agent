"""
配置管理模块（Pydantic V2）

沿用脚手架的多环境切换 + CORS + 日志配置；扩展 spec 要求的 DB / Redis / MinIO / JWT /
Bootstrap owner / Embedding 业务字段。

环境文件（位于 backend/ 根目录）：
- dev  -> .env.dev
- prod -> .env.prod
- test -> .env.test
也可用 ENV_FILE 显式指定绝对/相对路径。
"""

import os
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ 根目录（app/config/settings.py -> 上三级）
_BASE_PATH = Path(__file__).resolve().parent.parent.parent


def get_env_file() -> str:
    """根据 ENVIRONMENT / ENV_FILE 解析要加载的 env 文件路径。"""
    override = os.getenv("ENV_FILE", "").strip()
    if override:
        path = Path(override)
        if not path.is_absolute():
            path = _BASE_PATH / path
        return str(path)
    env = os.getenv("ENVIRONMENT", "dev").strip().lower()
    env_files = {
        "dev": ".env.dev",
        "prod": ".env.prod",
        "test": ".env.test",
    }
    target_file = env_files.get(env, f".env.{env}")
    return str(_BASE_PATH / target_file)


class Settings(BaseSettings):
    """应用配置类（Pydantic V2 BaseSettings）

    字段名即环境变量名（大小写敏感）。Docker 通过 env_file + 挂载 backend/.env.* 注入。
    """

    model_config = SettingsConfigDict(
        env_file=get_env_file(),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ========== 环境配置 ==========
    ENVIRONMENT: str = "dev"

    # ========== 应用基础配置 ==========
    APP_NAME: str = "LLM Wiki 3.0"
    APP_VERSION: str = "0.1.0"
    API_PREFIX: str = "/api/v1"
    DEBUG: bool = False
    AUTH_ENABLED: bool = True

    # ========== 服务器与 HTTP 配置 ==========
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    HTTP_TIMEOUT: int = 30

    # ========== CORS 配置 ==========
    ALLOW_ORIGINS: list[str] = ["*"]
    ALLOW_CREDENTIALS: bool = True
    ALLOW_METHODS: list[str] = ["*"]
    ALLOW_HEADERS: list[str] = ["*"]

    # ========== 日志 / 存储 ==========
    LOG_LEVEL: str = "INFO"
    # 默认 backend/logs；Docker 中通过 LOGS_DIR=/app/logs 并挂载 ./storage/logs/backend
    STORAGE_DIR: Path = Field(default_factory=lambda: _BASE_PATH / "storage")
    LOGS_DIR: Path = Field(default_factory=lambda: _BASE_PATH / "logs")
    LOG_RETENTION_DAYS: int = 30

    # ========== 数据库 ==========
    POSTGRES_DSN: str = ""  # postgresql+asyncpg://user:pwd@host:5432/dbname

    # ========== Redis ==========
    # Docker 内: redis://redis:6379/0；宿主机连容器: redis://localhost:6380/0
    REDIS_URL: str = "redis://localhost:6380/0"

    # ========== Taskiq Worker ==========
    TASK_WORKER_CONCURRENCY: int = 16
    TASK_CRITICAL_RESERVED_CONCURRENCY: int = 2
    TASK_PARSER_PROCESSES: int = 2
    TASK_LEASE_SECONDS: int = 900
    TASK_HEARTBEAT_SECONDS: int = 15
    TASK_STREAM_IDLE_TIMEOUT_MS: int = 1_800_000
    TASK_OUTBOX_BATCH_SIZE: int = 100
    TASK_OUTBOX_LOCK_SECONDS: int = 30
    TASK_OUTBOX_POLL_SECONDS: float = 0.5
    TASK_MAX_AUTO_RETRIES: int = 3
    TASK_RETRY_BASE_SECONDS: int = 5
    TASK_RETRY_MAX_SECONDS: int = 300

    # ========== MinIO ==========
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = ""
    MINIO_SECRET_KEY: str = ""
    MINIO_BUCKET: str = "llm-wiki"
    MINIO_SECURE: bool = False

    # ========== JWT ==========
    JWT_SECRET: str = ""
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = 24

    # ========== Bootstrap owner ==========
    BOOTSTRAP_OWNER_EMAIL: str = ""
    BOOTSTRAP_OWNER_PASSWORD: str = ""

    # ========== Embedding ==========
    # 默认 Jina Embeddings（OpenAI 兼容协议）
    EMBEDDING_API_BASE: str = "https://api.jina.ai/v1"
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_MODEL: str = "jina-embeddings-v5-text-small"
    EMBEDDING_DIM: int = 1024

    # ========== 文档解析生产护栏 ==========
    # 字节数配置：50 MiB = 50 * 1024 * 1024 bytes
    PARSER_MAX_FILE_BYTES: int = 50 * 1024 * 1024
    PARSER_MAX_OUTPUT_CHARS: int = 5_000_000
    # 字节数配置：20 MiB = 20 * 1024 * 1024 bytes
    PARSER_MAX_TOTAL_IMAGE_BYTES: int = 20 * 1024 * 1024
    PARSER_TIMEOUT_SECONDS: int = 300
    # ========== RAG 检索 ==========
    RAG_TOP_K_EACH: int = 20
    RAG_RRF_K: int = 60

    @field_validator("STORAGE_DIR", "LOGS_DIR", mode="before")
    @classmethod
    def _parse_path(cls, value: object) -> Path:
        """将环境变量中的路径字符串规范为 Path。"""
        if value is None or value == "":
            raise ValueError("path setting must not be empty")
        return Path(str(value))


# 全局配置实例
settings = Settings()
