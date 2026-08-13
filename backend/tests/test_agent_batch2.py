"""
Batch 2 行为契约测试：agent 模块骨架（pipeline / schemas / llm_client）

TDD 契约（对应 P1 spec §4.2）：
- EventManager.PIPELINE = SEARCH -> FILTER_TOP_K -> INTO_CHAT_MESSAGE -> GENERATE -> FORMAT_CITATIONS
- Plugin.on_event 只在匹配事件执行；ChatContext 在插件间传递状态
- LLMClient 端点 = base_url + "/v1/chat/completions"，SSE 逐 token yield
- 超时最多 3 次尝试；401 立即抛 ModelKeyInvalidError 不重试
"""
import httpx
import pytest

from app.core.exceptions import LLMTimeoutError, ModelKeyInvalidError
from app.integrations.chat_llm import LLMClient
from app.agent.plugins import ChatContext, EventManager, Plugin
from app.agent.api.schemas import ChatRequest, Citation


# ============================ schemas ============================

class TestCitation:
    def test_fields(self):
        citation = Citation(id=1, title="产品规格书", source="manual", chunk_id=123)
        assert citation.id == 1
        assert citation.title == "产品规格书"
        assert citation.source == "manual"
        assert citation.chunk_id == 123


class TestChatRequest:
    def test_default_limit_is_5(self):
        request = ChatRequest(query="产品支持 5G 吗？")
        assert request.query == "产品支持 5G 吗？"
        assert request.limit == 5

    def test_custom_limit(self):
        request = ChatRequest(query="产品支持 5G 吗？", limit=10)
        assert request.limit == 10


# ============================ pipeline ============================

class TestChatContext:
    def test_fields(self):
        context = ChatContext(query="q", kb_id=1, tenant_id=2, limit=5)
        assert context.query == "q"
        assert context.kb_id == 1
        assert context.tenant_id == 2
        assert context.limit == 5
        assert context.chunks == []
        assert context.prompt is None
        assert context.answer is None
        assert context.citations == []
        assert context.error is None


class TestPluginEventFiltering:
    """Plugin 只在 EventManager 到达其声明的事件时被调用。"""

    async def test_runs_only_on_own_event(self):
        calls = []

        class ProbePlugin(Plugin):
            event = "GENERATE"

            async def on_event(self, event, context):
                calls.append(event)

        manager = EventManager([ProbePlugin()])
        await manager.run(ChatContext(query="q", kb_id=1, tenant_id=2))
        # PIPELINE 共 5 个事件，ProbePlugin 只应在 GENERATE 被调用一次
        assert calls == ["GENERATE"]

    async def test_state_passes_between_plugins(self):
        context = ChatContext(query="q", kb_id=1, tenant_id=2)

        class WritePlugin(Plugin):
            event = "SEARCH"

            async def on_event(self, event, context):
                context.prompt = "built prompt"

        class ReadPlugin(Plugin):
            event = "GENERATE"

            async def on_event(self, event, context):
                assert context.prompt == "built prompt"
                context.answer = "final answer"

        manager = EventManager([WritePlugin(), ReadPlugin()])
        await manager.run(context)
        assert context.answer == "final answer"


class TestEventManager:
    def test_pipeline_order(self):
        assert EventManager.PIPELINE == [
            "SEARCH",
            "FILTER_TOP_K",
            "INTO_CHAT_MESSAGE",
            "GENERATE",
            "FORMAT_CITATIONS",
        ]

    async def test_runs_events_in_pipeline_order(self):
        """全部插件按 PIPELINE 声明顺序执行，而非插件注册顺序。"""
        order = []

        def make_plugin(name):
            class OrderedPlugin(Plugin):
                event = name

                async def on_event(self, event, context):
                    order.append(name)
            return OrderedPlugin()

        # 故意逆序注册
        plugins = [make_plugin(e) for e in reversed(EventManager.PIPELINE)]
        manager = EventManager(plugins)
        await manager.run(ChatContext(query="q", kb_id=1, tenant_id=2))
        assert order == EventManager.PIPELINE


# ============================ llm_client ============================

class TestLLMClient:
    def _sse_response(self, chunks: list[str]) -> httpx.Response:
        """构造 OpenAI 兼容 SSE 响应。"""
        body = ""
        for chunk in chunks:
            body += 'data: {"choices":[{"delta":{"content":"%s"}}]}\n\n' % chunk
        body += "data: [DONE]\n\n"
        return httpx.Response(200, text=body)

    def _make_client(self, handler, timeout_seconds: float = 5.0) -> LLMClient:
        transport = httpx.MockTransport(handler)
        http_client = httpx.AsyncClient(transport=transport)
        return LLMClient(
            base_url="https://api.deepseek.com",
            api_key="sk-test-key",
            model="deepseek-v4-flash",
            timeout_seconds=timeout_seconds,
            http_client=http_client,
        )

    async def test_request_url_and_auth_header(self):
        captured = {}

        async def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["auth"] = request.headers.get("authorization")
            captured["body"] = request.content
            return self._sse_response(["ok"])

        client = self._make_client(handler)
        chunks = [chunk async for chunk in client.stream_chat(
            [{"role": "user", "content": "你好"}],
        )]
        assert chunks == ["ok"]
        assert captured["url"] == "https://api.deepseek.com/v1/chat/completions"
        assert captured["auth"] == "Bearer sk-test-key"

    async def test_sse_streams_multiple_tokens(self):
        client = self._make_client(
            lambda request: self._sse_response(["你", "好", "世界"]),
        )
        chunks = [chunk async for chunk in client.stream_chat([{"role": "user", "content": "hi"}])]
        assert chunks == ["你", "好", "世界"]

    async def test_retries_on_timeout_up_to_3_attempts(self):
        """前两次 ConnectTimeout，第三次成功——共 3 次尝试。"""
        attempts = {"count": 0}

        async def handler(request: httpx.Request) -> httpx.Response:
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise httpx.ConnectTimeout("timeout", request=request)
            return self._sse_response(["终于成功"])

        client = self._make_client(handler)
        chunks = [chunk async for chunk in client.stream_chat([{"role": "user", "content": "hi"}])]
        assert chunks == ["终于成功"]
        assert attempts["count"] == 3

    async def test_raises_timeout_error_after_3_attempts(self):
        attempts = {"count": 0}

        async def handler(request: httpx.Request) -> httpx.Response:
            attempts["count"] += 1
            raise httpx.ConnectTimeout("timeout", request=request)

        client = self._make_client(handler)
        with pytest.raises(LLMTimeoutError):
            async for _ in client.stream_chat([{"role": "user", "content": "hi"}]):
                pass
        assert attempts["count"] == 3

    async def test_401_raises_key_invalid_without_retry(self):
        attempts = {"count": 0}

        async def handler(request: httpx.Request) -> httpx.Response:
            attempts["count"] += 1
            return httpx.Response(401, json={"error": {"message": "Invalid API key"}})

        client = self._make_client(handler)
        with pytest.raises(ModelKeyInvalidError):
            async for _ in client.stream_chat([{"role": "user", "content": "hi"}]):
                pass
        assert attempts["count"] == 1

    async def test_timeout_error_contains_attempts(self):
        async def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectTimeout("timeout", request=request)

        client = self._make_client(handler)
        with pytest.raises(LLMTimeoutError) as excinfo:
            async for _ in client.stream_chat([{"role": "user", "content": "hi"}]):
                pass
        assert "3" in str(excinfo.value)
