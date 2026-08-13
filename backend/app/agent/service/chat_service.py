"""
chat_service：Agent 流水线组装层（P1 spec #12 端点 + 方案 A 注入式组装）

职责：
- 从 DB 读 KB 绑定的 chat 模型配置并解密 api_key（load_chat_model_config）
- 组装 5 个 Plugin + EventManager，注入依赖（db / LLMClient / token_sink）
- 流式产出 SSE 事件 dict：token（逐段答案）/ done（答案+引用）/ error（Key 失效）

插件保持纯业务，DB 读取与连接创建都在本层完成。
"""
import asyncio
import logging

from app.agent.plugins import ChatContext, EventManager
from app.agent.plugins.filter_top_k import FilterTopKPlugin
from app.agent.plugins.format_citations import FormatCitationsPlugin
from app.agent.plugins.generate import GeneratePlugin
from app.agent.plugins.into_chat_message import IntoChatMessagePlugin
from app.agent.plugins.search import SearchPlugin
from app.agent.repository.model_repo import ModelRepository
from app.config.settings import settings
from app.core.crypto import decrypt_secret, derive_key
from app.integrations.chat_llm import LLMClient

logger = logging.getLogger(__name__)


async def load_chat_model_config(kb_id: int, db) -> dict:
    """读 KB 绑定的 chat 模型配置并解密 api_key。

    数据访问走 repository（ModelRepository.get_chat_parameters）；
    本层只做业务规则：解密密文 + 组装返回 dict。
    """
    name, parameters = await ModelRepository(db).get_chat_parameters(kb_id)
    api_key = decrypt_secret(
        parameters["api_key"],
        derive_key(settings.MODEL_ENCRYPTION_KEY or settings.JWT_SECRET),
    )
    return {
        "base_url": parameters["base_url"],
        "api_key": api_key,
        "model": parameters.get("model_name") or name,
    }


async def run_chat(
    db,
    kb_id: int,
    tenant_id: int,
    query: str,
    limit: int = 5,
):
    """执行 Agent 流水线，流式产出 SSE 事件 dict。"""
    config = await load_chat_model_config(kb_id, db)
    llm_client = LLMClient(
        base_url=config["base_url"],
        api_key=config["api_key"],
        model=config["model"],
    )
    context = ChatContext(
        query=query,
        kb_id=kb_id,
        tenant_id=tenant_id,
        limit=limit,
    )
    queue: asyncio.Queue = asyncio.Queue()

    async def token_sink(token: str) -> None:
        await queue.put(("token", token))

    plugins = [
        SearchPlugin(db),
        FilterTopKPlugin(),
        IntoChatMessagePlugin(),
        GeneratePlugin(llm_client, token_sink=token_sink),
        FormatCitationsPlugin(),
    ]
    manager = EventManager(plugins)

    async def _run_then_signal() -> None:
        await manager.run(context)
        await queue.put(("done", None))

    task = asyncio.create_task(_run_then_signal())
    while True:
        event_type, payload = await queue.get()
        if event_type == "token":
            yield {"type": "token", "text": payload}
        elif event_type == "done":
            break
    await task

    if context.error == "MODEL_KEY_INVALID":
        yield {
            "type": "error",
            "code": "MODEL_KEY_INVALID",
            "message": "对话模型 Key 失效，请检查系统配置",
        }
        return
    yield {
        "type": "done",
        "answer": context.answer,
        "citations": context.citations,
    }
