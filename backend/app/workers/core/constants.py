"""Workers 常量与枚举：统一管理，避免四处分散。

所有业务常量（状态 / 类型 / 错误码 / Span 名称 / 队列名）集中在此，
其他模块通过 `from app.workers.core.constants import RunStatus, ...` 引用。
用 `str, Enum` 而非 `StrEnum`，兼容 Python 3.10+。
"""

from enum import Enum


class RunStatus(str, Enum):
    """Run 运行状态。"""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SpanStatus(str, Enum):
    """Span 阶段状态。"""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class RunType(str, Enum):
    """Run 业务类型。"""

    SOURCE_SYNC = "source_sync"
    DOCUMENT_PROCESS = "document_process"
    RAG_INDEX = "rag_index"
    WIKI_GENERATE = "wiki_generate"


class ScopeType(str, Enum):
    """Run 处理目标类型。"""

    SOURCE = "source"
    REVISION = "revision"
    KNOWLEDGE_BASE = "knowledge_base"
    WIKI_PAGE = "wiki_page"


class TriggerType(str, Enum):
    """Run 触发方式。"""

    MANUAL = "manual"
    ON_INGEST = "on_ingest"
    SYSTEM = "system"
    SCHEDULE = "schedule"
    RETRY = "retry"


class ErrorCode(str, Enum):
    """稳定机器错误码。"""

    ENQUEUE_FAILED = "enqueue_failed"
    REAPER_RECOVERED = "reaper_recovered"
    MIDDLEWARE_FAILURE = "middleware_failure"
    UNKNOWN_RUN_TYPE = "unknown_run_type"
    HANDLER_CONTRACT_VIOLATION = "handler_contract_violation"
    CANDIDATE_CHUNKS_EXIST = "candidate_chunks_exist"
    CANDIDATE_CHUNKS_MISSING = "candidate_chunks_missing"
    CANDIDATE_CHUNKS_INDEXED = "candidate_chunks_indexed"
    CANDIDATE_CHUNKS_CHANGED = "candidate_chunks_changed"
    EMPTY_CONTENT = "empty_content"
    KB_NOT_FOUND = "kb_not_found"
    REVISION_NOT_FOUND = "revision_not_found"
    DOCUMENT_NOT_FOUND = "document_not_found"
    INVALID_SCOPE = "invalid_scope"
    TIMEOUT = "timeout"
    EMBEDDING_COUNT_MISMATCH = "embedding_count_mismatch"
    EMBEDDING_DIMENSION_MISMATCH = "embedding_dimension_mismatch"
    UNEXPECTED_EXCEPTION = "unexpected_exception"


class SpanName(str, Enum):
    """Span 阶段名称。"""

    WORKER_ATTEMPT = "worker_attempt"
    PARSE = "parse"
    PERSIST = "persist"
    EMBED = "embed"
    ACTIVATE = "activate"


# 队列名（Dramatiq 队列标识）
CRITICAL_QUEUE: str = "critical"
DEFAULT_QUEUE: str = "default"

# Run 类型 -> 队列映射（critical 队列的 Run 类型）
CRITICAL_RUN_TYPES: frozenset[RunType] = frozenset({RunType.RAG_INDEX, RunType.SOURCE_SYNC})
