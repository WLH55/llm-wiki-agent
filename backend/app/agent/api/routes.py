"""
Agent 路由：POST /api/v1/kb/{kb_id}/chat（SSE 流式，P1 spec #12）

路由层职责：参数校验 + 调 service + SSE 适配；不写 try/except。
SSE 事件格式（P1 spec §4.5）：
- event: token  data: {"text": "..."}
- event: done   data: {"answer": "...", "citations": [...]}
- event: error  data: {"code": "MODEL_KEY_INVALID", "message": "..."}
"""
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.agent.api.schemas import ChatRequest
from app.agent.service.chat_service import run_chat
from app.auth.api.dependencies import CurrentUserDep
from app.web.dependencies import DbDep

router = APIRouter(prefix="/kb", tags=["知识库问答"])


def _sse(event: str, data: dict) -> str:
    """格式化一条 SSE 消息。"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/{kb_id}/chat")
async def chat_endpoint(
    kb_id: int,
    payload: ChatRequest,
    db: DbDep,
    user: CurrentUserDep,
) -> StreamingResponse:
    """知识库问答：SSE 流式返回答案与引用。"""
    async def event_stream():
        async for event in run_chat(
            db=db,
            kb_id=kb_id,
            tenant_id=user.tenant_id,
            query=payload.query,
            limit=payload.limit,
        ):
            # citations 是 pydantic 模型列表，序列化为 dict
            if event["type"] == "done":
                event["citations"] = [
                    citation.model_dump() for citation in event["citations"]
                ]
            yield _sse(event["type"], event)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
