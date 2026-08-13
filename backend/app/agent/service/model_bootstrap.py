"""
启动/请求时确保默认模型存在（MVP env var 初始化，ADR-0020）

业务编排层：环境变量判断、api_key 加密等业务规则在此；
models/tenants 表的读写走 repository（agent.repository.ModelRepository /
auth.repository.TenantRepository）。

- 取默认 tenant（MVP 单租户，第一个 tenant）
- chat 模型：CHAT_API_BASE / CHAT_API_KEY / CHAT_MODEL / CHAT_TIMEOUT_SECONDS
- embedding 模型：EMBEDDING_API_BASE / EMBEDDING_API_KEY / EMBEDDING_MODEL / EMBEDDING_DIM
- api_key 用 AES-256-GCM 加密后存 parameters（app/core/crypto.py）
- 幂等：按 (tenant_id, model_type, name) 判断，存在则跳过；env 未配置时快速失败

注意：不走 lifespan（tests/test_main.py 契约断言 lifespan 不初始化 bootstrap），
由 agent 端点依赖链调用，每次请求幂等 ensure，开销为一次 SELECT。
"""
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.repository.model_repo import ModelRepository
from app.auth.repository.user_repo import TenantRepository
from app.config.settings import settings
from app.core.crypto import derive_key, encrypt_secret
from app.models.model import (
    MODEL_SOURCE_OPENAI,
    MODEL_TYPE_CHAT,
    MODEL_TYPE_EMBEDDING,
)

logger = logging.getLogger(__name__)


def _encryption_key() -> bytes:
    """加密密钥：MODEL_ENCRYPTION_KEY 优先，回退 JWT_SECRET 派生。"""
    secret = settings.MODEL_ENCRYPTION_KEY or settings.JWT_SECRET
    if not secret:
        raise RuntimeError("MODEL_ENCRYPTION_KEY 与 JWT_SECRET 均未配置，无法加密 api_key")
    return derive_key(secret)


async def _ensure_one(
    repo: ModelRepository,
    tenant_id: int,
    model_type: str,
    name: str,
    base_url: str,
    api_key: str,
    extra_params: dict,
) -> int:
    """幂等创建单个模型配置，返回 model_id。

    加密 api_key 属于业务规则（service 层职责），repository 只存不加工。
    """
    model_id = await repo.find_id(tenant_id, model_type, name)
    if model_id is not None:
        return model_id
    encrypted_key = encrypt_secret(api_key, _encryption_key())
    parameters = {
        "base_url": base_url,
        "api_key": encrypted_key,
        **extra_params,
    }
    model_id = await repo.create(
        tenant_id=tenant_id,
        name=name,
        model_type=model_type,
        source=MODEL_SOURCE_OPENAI,
        parameters=parameters,
    )
    logger.info("默认模型已写入: type=%s name=%s id=%s", model_type, name, model_id)
    return model_id


async def ensure_default_models(db: AsyncSession) -> tuple[int, int]:
    """确保默认 chat + embedding 模型存在，返回 (chat_model_id, embedding_model_id)。

    - 无 tenant 时直接失败（bootstrap owner 尚未创建，聊天不可用）
    - chat / embedding env 未配置时快速失败（不吞错误）
    """
    tenant_repo = TenantRepository(db)
    tenant = await tenant_repo.get_first()
    if tenant is None:
        raise RuntimeError("tenants 表为空，无法初始化默认模型（需先创建 bootstrap owner）")

    if not settings.CHAT_API_KEY:
        raise RuntimeError("CHAT_API_KEY 未配置，无法初始化 chat 模型")
    if not settings.EMBEDDING_API_KEY:
        raise RuntimeError("EMBEDDING_API_KEY 未配置，无法初始化 embedding 模型")

    model_repo = ModelRepository(db)
    chat_model_id = await _ensure_one(
        model_repo,
        tenant.id,
        MODEL_TYPE_CHAT,
        settings.CHAT_MODEL,
        settings.CHAT_API_BASE,
        settings.CHAT_API_KEY,
        {
            "model_name": settings.CHAT_MODEL,
            "timeout_seconds": settings.CHAT_TIMEOUT_SECONDS,
        },
    )
    embedding_model_id = await _ensure_one(
        model_repo,
        tenant.id,
        MODEL_TYPE_EMBEDDING,
        settings.EMBEDDING_MODEL,
        settings.EMBEDDING_API_BASE,
        settings.EMBEDDING_API_KEY,
        {
            "model_name": settings.EMBEDDING_MODEL,
            "dimension": settings.EMBEDDING_DIM,
        },
    )
    return chat_model_id, embedding_model_id
