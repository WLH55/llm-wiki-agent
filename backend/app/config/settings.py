"""
配置管理模块（Pydantic V2）

沿用脚手架的多环境切换 + CORS + 日志配置；扩展 spec 要求的 DB / Redis / MinIO / JWT /
Bootstrap owner / Embedding 业务字段。
"""
import os
from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


# 提取基础路径（常量）
_BASE_PATH = Path(__file__).resolve().parent.parent.parent


def get_env_file() -> str:
    """根据环境变量 ENVIRONMENT 获取 .env 文件路径"""
    env = os.getenv("ENVIRONMENT", "development")
    env_files = {
        "development": ".env.development",
        "production": ".env.production",
        "test": ".env.test",
    }
    target_file = env_files.get(env, ".env.development")
    return str(_BASE_PATH / target_file)


class Settings(BaseSettings):
    """应用配置类（Pydantic V2 BaseSettings）

    沿用脚手架字段命名风格（大写），保证 env_file 加载时大小写敏感。
    """

    model_config = SettingsConfigDict(
        env_file=get_env_file(),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ========== 环境配置（沿用脚手架） ==========
    ENVIRONMENT: str = "development"

    # ========== 应用基础配置（沿用脚手架） ==========
    APP_NAME: str = "LLM Wiki 3.0"
    APP_VERSION: str = "0.1.0"
    API_PREFIX: str = "/api/v1"
    DEBUG: bool = False

    # ========== 服务器与 HTTP 配置（沿用脚手架） ==========
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    HTTP_TIMEOUT: int = 30

    # ========== CORS 配置（沿用脚手架） ==========
    ALLOW_ORIGINS: List[str] = ["*"]
    ALLOW_CREDENTIALS: bool = True
    ALLOW_METHODS: List[str] = ["*"]
    ALLOW_HEADERS: List[str] = ["*"]

    # ========== 日志配置（沿用脚手架） ==========
    LOG_LEVEL: str = "INFO"
    STORAGE_DIR: Path = _BASE_PATH / "storage"
    LOGS_DIR: Path = _BASE_PATH / "storage" / "logs"
    LOG_RETENTION_DAYS: int = 30

    # ========== 数据库配置（spec 扩展） ==========
    POSTGRES_DSN: str = ""  # postgresql+asyncpg://user:pwd@host:5432/dbname

    # ========== Redis 配置（spec 扩展） ==========
    REDIS_URL: str = "redis://localhost:6379/0"

    # ========== MinIO 配置（spec 扩展） ==========
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = ""
    MINIO_SECRET_KEY: str = ""
    MINIO_BUCKET: str = "llm-wiki"
    MINIO_SECURE: bool = False

    # ========== JWT 配置（spec 扩展，HS256，24h） ==========
    JWT_SECRET: str = ""
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = 24

    # ========== Bootstrap owner 配置（spec 扩展） ==========
    BOOTSTRAP_OWNER_EMAIL: str = ""
    BOOTSTRAP_OWNER_PASSWORD: str = ""

    # ========== Embedding 配置（spec 扩展，SiliconFlow bge-m3） ==========
    EMBEDDING_API_BASE: str = "https://api.siliconflow.cn/v1"
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_MODEL: str = "BAAI/bge-m3"
    EMBEDDING_DIM: int = 1024

    # ========== RAG 检索配置（spec 扩展） ==========
    RAG_TOP_K_EACH: int = 20  # 向量 / BM25 各自召回 top-K
    RAG_RRF_K: int = 60       # RRF 融合常数，经验默认值

    # ========== 前端静态托管配置（spec 扩展，无 nginx） ==========
    FRONTEND_DIST_DIR: Path = _BASE_PATH / "static" / "dist"


# 全局配置实例
settings = Settings()
