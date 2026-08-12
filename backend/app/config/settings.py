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

    # ========== Task Worker ==========
    # Reaper 扫描间隔（秒）--嵌入 worker 进程的独立线程
    TASK_REAPER_INTERVAL_SECONDS: int = 300
    # Span 心跳超时阈值（秒）--running Run 的 MAX(spans.updated_at) 超此阈值视为卡死
    # 70min：embedding 5K chunks 可能跑 15min，15min << 70min，粗粒度 span 安全（对齐 WeKnora）
    TASK_SPAN_STALE_SECONDS: int = 4200
    # Pending Run 过旧阈值（秒）--pending Run 的 updated_at 超此阈值视为卡死（入队失败/丢失）
    TASK_PENDING_STALE_SECONDS: int = 300
    # Dramatiq actor 单消息最大执行时长（毫秒）--统一 1h
    TASK_TIME_LIMIT_MS: int = 3_600_000

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
    # 各路过检索 top_k（过检索后再融合截断）
    RAG_TOP_K_EACH: int = 20
    # RRF 融合常数 k（WeKnora 同款）
    RAG_RRF_K: int = 60
    # 向量相似度阈值（score=1-distance，低于此值过滤）
    RAG_VECTOR_THRESHOLD: float = 0.15
    # BM25 关键词分数阈值（paradedb.score 归一化 0-1，低于此值过滤）
    RAG_KEYWORD_THRESHOLD: float = 0.3
    # 过检索倍数（各路候选 = limit * factor）
    RAG_OVER_RETRIEVE_FACTOR: int = 5
    # 过检索最少候选数（clamp 下限）
    RAG_OVER_RETRIEVE_MIN: int = 50
    # 过检索最多候选数（clamp 上限）
    RAG_OVER_RETRIEVE_CAP: int = 500
    # RRF 向量路权重
    RAG_RRF_VECTOR_WEIGHT: float = 0.7
    # RRF 关键词路权重
    RAG_RRF_KEYWORD_WEIGHT: float = 0.3

    @field_validator("STORAGE_DIR", "LOGS_DIR", mode="before")
    @classmethod
    def _parse_path(cls, value: object) -> Path:
        """将环境变量中的路径字符串规范为 Path。"""
        if value is None or value == "":
            raise ValueError("path setting must not be empty")
        return Path(str(value))


# 全局配置实例
settings = Settings()
