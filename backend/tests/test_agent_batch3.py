"""
Batch 3 行为契约测试：5 个 Plugin + chat_service 全链路（P1 spec #7-12）

契约要点：
- FilterTopKPlugin 截断到 limit
- IntoChatMessagePlugin 按顺序分配 citation_id + XML 渲染 + 严格模式 Prompt；空 chunks 不渲染
- FormatCitationsPlugin 提取答案 [N] 标注 -> 映射 chunk -> Citation 列表
- GeneratePlugin 空 chunks 固定话术不调 LLM；流式 token 拼接 + sink；Key 失效 -> error
- SearchPlugin 调 retrieval.search 结果写入 chunks
- chat_service.run_chat 全链路产出 done 事件含 citations
"""
import pytest

from app.agent.api.schemas import Citation
from app.agent.plugins import ChatContext
from app.agent.plugins.filter_top_k import FilterTopKPlugin
from app.agent.plugins.format_citations import FormatCitationsPlugin
from app.agent.plugins.into_chat_message import IntoChatMessagePlugin
from app.agent.plugins.generate import GeneratePlugin
from app.agent.plugins.search import SearchPlugin
from app.core.exceptions import ModelKeyInvalidError
from app.knowledge_bases.api.schemas import RetrievalResult

# 无结果固定话术（P1 spec §4.4）
NO_RESULT_ANSWER = "根据知识库中的信息，无法回答该问题。"


def make_chunk(
    chunk_id: int,
    text: str = "chunk 正文",
    title: str = "测试文档",
    source_type: str = "markdown",
) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=chunk_id,
        document_id=100 + chunk_id,
        revision_id=200 + chunk_id,
        score=0.8,
        text=text,
        chunk_index=chunk_id - 1,
        document_title=title,
        source_type=source_type,
    )


def make_context(limit: int = 5) -> ChatContext:
    return ChatContext(query="测试问题", kb_id=1, tenant_id=1, limit=limit)


# ==================== FilterTopKPlugin ====================

class TestFilterTopKPlugin:
    def test_event(self):
        assert FilterTopKPlugin.event == "FILTER_TOP_K"

    async def test_truncates_to_limit(self):
        context = make_context(limit=2)
        context.chunks = [make_chunk(i) for i in range(1, 6)]
        await FilterTopKPlugin().on_event("FILTER_TOP_K", context)
        assert [c.chunk_id for c in context.chunks] == [1, 2]

    async def test_keeps_when_below_limit(self):
        context = make_context(limit=5)
        context.chunks = [make_chunk(1), make_chunk(2)]
        await FilterTopKPlugin().on_event("FILTER_TOP_K", context)
        assert len(context.chunks) == 2


# ==================== IntoChatMessagePlugin ====================

class TestIntoChatMessagePlugin:
    def test_event(self):
        assert IntoChatMessagePlugin.event == "INTO_CHAT_MESSAGE"

    async def test_assigns_citation_ids_in_order(self):
        context = make_context()
        context.chunks = [make_chunk(10), make_chunk(11)]
        await IntoChatMessagePlugin().on_event("INTO_CHAT_MESSAGE", context)
        assert [c.citation_id for c in context.chunks] == [1, 2]

    async def test_xml_structure(self):
        context = make_context()
        context.chunks = [make_chunk(10, text="产品支持 5G 网络")]
        await IntoChatMessagePlugin().on_event("INTO_CHAT_MESSAGE", context)
        assert context.prompt is not None
        assert "<documents>" in context.prompt
        assert '<context id="1">' in context.prompt
        assert "产品支持 5G 网络" in context.prompt

    async def test_strict_mode_prompt_rules(self):
        context = make_context()
        context.chunks = [make_chunk(10)]
        await IntoChatMessagePlugin().on_event("INTO_CHAT_MESSAGE", context)
        # 严格模式三规则（P1 spec §4.4）
        assert "禁止使用先验知识" in context.prompt
        assert "[N]" in context.prompt
        assert NO_RESULT_ANSWER in context.prompt

    async def test_empty_chunks_no_prompt(self):
        context = make_context()
        await IntoChatMessagePlugin().on_event("INTO_CHAT_MESSAGE", context)
        assert context.prompt is None


# ==================== FormatCitationsPlugin ====================

class TestFormatCitationsPlugin:
    def test_event(self):
        assert FormatCitationsPlugin.event == "FORMAT_CITATIONS"

    async def test_extracts_numbered_citations(self):
        context = make_context()
        context.chunks = [
            make_chunk(10, title="产品规格书", source_type="markdown"),
            make_chunk(11, title="用户手册", source_type="pdf"),
        ]
        await IntoChatMessagePlugin().on_event("INTO_CHAT_MESSAGE", context)
        context.answer = "该产品支持 5G [1]，续航 10 小时 [2]。"
        await FormatCitationsPlugin().on_event("FORMAT_CITATIONS", context)
        assert context.citations == [
            Citation(id=1, title="产品规格书", source="markdown", chunk_id=10),
            Citation(id=2, title="用户手册", source="pdf", chunk_id=11),
        ]

    async def test_no_annotation_gives_empty(self):
        context = make_context()
        context.chunks = [make_chunk(10)]
        await IntoChatMessagePlugin().on_event("INTO_CHAT_MESSAGE", context)
        context.answer = "无标注的回答"
        await FormatCitationsPlugin().on_event("FORMAT_CITATIONS", context)
        assert context.citations == []


# ==================== SearchPlugin ====================

class TestSearchPlugin:
    def test_event(self):
        assert SearchPlugin.event == "SEARCH"

    async def test_writes_search_results(self, monkeypatch):
        async def fake_search(db, kb_id, query, limit=10):
            return [make_chunk(1), make_chunk(2)]

        monkeypatch.setattr("app.agent.plugins.search.search", fake_search)
        context = make_context()
        await SearchPlugin(db=None).on_event("SEARCH", context)
        assert [c.chunk_id for c in context.chunks] == [1, 2]


# ==================== GeneratePlugin ====================

class FakeLLMClient:
    """记录调用 + 可控输出的假 LLM 客户端。"""

    def __init__(self, tokens: list[str] | None = None, error: Exception | None = None):
        self.tokens = tokens or []
        self.error = error
        self.calls: list[list[dict]] = []

    async def stream_chat(self, messages, temperature=0.3):
        self.calls.append(messages)
        if self.error is not None:
            raise self.error
        for token in self.tokens:
            yield token


class TestGeneratePlugin:
    def test_event(self):
        assert GeneratePlugin.event == "GENERATE"

    async def test_empty_chunks_fallback_without_calling_llm(self):
        fake_client = FakeLLMClient(tokens=["不应该被调用"])
        context = make_context()
        await GeneratePlugin(fake_client).on_event("GENERATE", context)
        assert context.answer == NO_RESULT_ANSWER
        assert fake_client.calls == []

    async def test_streams_and_concatenates_tokens(self):
        fake_client = FakeLLMClient(tokens=["你", "好", "世界"])
        sink_tokens = []
        async def sink(token):
            sink_tokens.append(token)

        context = make_context()
        context.chunks = [make_chunk(1)]
        await IntoChatMessagePlugin().on_event("INTO_CHAT_MESSAGE", context)
        await GeneratePlugin(fake_client, token_sink=sink).on_event("GENERATE", context)
        assert context.answer == "你好世界"
        assert sink_tokens == ["你", "好", "世界"]
        assert len(fake_client.calls) == 1

    async def test_key_invalid_sets_error(self):
        fake_client = FakeLLMClient(error=ModelKeyInvalidError("Key 失效"))
        context = make_context()
        context.chunks = [make_chunk(1)]
        await IntoChatMessagePlugin().on_event("INTO_CHAT_MESSAGE", context)
        await GeneratePlugin(fake_client).on_event("GENERATE", context)
        assert context.error == "MODEL_KEY_INVALID"


# ==================== chat_service 全链路 ====================

class TestChatService:
    async def test_run_chat_full_pipeline(self, monkeypatch):
        from app.agent.service import chat_service

        # 假模型配置读取（绕过 DB 解密）
        async def fake_load(kb_id, db):
            return {"base_url": "https://fake.example", "api_key": "sk-fake", "model": "fake-model"}

        monkeypatch.setattr(chat_service, "load_chat_model_config", fake_load)

        # 假检索（绕过 DB）
        async def fake_search(db, kb_id, query, limit=10):
            return [make_chunk(1, text="产品支持 5G 网络")]

        monkeypatch.setattr("app.agent.plugins.search.search", fake_search)

        # 假 LLM 客户端工厂（绕过真实网络）
        fake_client = FakeLLMClient(tokens=["产品支持 5G [1]"])
        monkeypatch.setattr(
            chat_service,
            "LLMClient",
            lambda **kwargs: fake_client,
        )

        events = [event async for event in chat_service.run_chat(
            db=None, kb_id=1, tenant_id=1, query="产品支持 5G 吗", limit=5,
        )]

        # done 事件含答案与引用
        done_events = [e for e in events if e["type"] == "done"]
        assert len(done_events) == 1
        done = done_events[0]
        assert done["answer"] == "产品支持 5G [1]"
        assert done["citations"] == [
            Citation(id=1, title="测试文档", source="markdown", chunk_id=1)
        ]

    async def test_run_chat_no_result_fallback(self, monkeypatch):
        from app.agent.service import chat_service

        async def fake_load(kb_id, db):
            return {"base_url": "https://fake.example", "api_key": "sk-fake", "model": "fake-model"}

        monkeypatch.setattr(chat_service, "load_chat_model_config", fake_load)

        async def fake_search(db, kb_id, query, limit=10):
            return []

        monkeypatch.setattr("app.agent.plugins.search.search", fake_search)

        fake_client = FakeLLMClient(tokens=["不该被调用"])
        monkeypatch.setattr(chat_service, "LLMClient", lambda **kwargs: fake_client)

        events = [event async for event in chat_service.run_chat(
            db=None, kb_id=1, tenant_id=1, query="不存在的主题", limit=5,
        )]

        done = [e for e in events if e["type"] == "done"][0]
        assert done["answer"] == NO_RESULT_ANSWER
        assert done["citations"] == []
        assert fake_client.calls == []
