# 任务队列设计文档

> 基于 Dramatiq + Redis 的任务队列，借鉴 WeKnora 的 housekeeping + span 心跳兜底哲学。
> 无 fencing CAS、无 Outbox 投递层，靠 span 心跳 + Reaper 兜底。

---

## 1. 整体架构

### 1.1 设计哲学

| 原则 | 实现 |
|---|---|
| **直接入队** | DB 提交后 `actor.send(run_id)` 直接入 Redis，无 Outbox 中间层 |
| **崩溃重投** | Dramatiq RedisBroker 的 `heartbeat_timeout=60s`：worker 进程崩溃后 60s 未 ack 的消息被放回队列 |
| **自动重试** | Dramatiq Retries middleware：handler 抛异常时按 `max_retries=3` + 指数退避重试 |
| **死信回调** | `throws=(TerminalTaskError,)`：终态错误直接进死信，不重试 |
| **span 心跳** | handler 各阶段调 `begin_span`/`end_span`，刷 `spans.updated_at` 作为心跳 |
| **Reaper 兜底** | 嵌入 worker 的独立线程，每 5min 扫描卡死 Run（span 心跳超 70min / pending 过 5min）标 failed |
| **无 fencing** | 不写 `execution_token`/`epoch`/`lease`，靠 `claim_run` 的 CAS `pending->running` 吸收重复投递 |

### 1.2 组件拓扑

```
┌─────────────────────────────────────────────────────────────┐
│  FastAPI 进程（backend 容器）                                │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  API 路由 → document.py / rag_ingestion.py           │   │
│  │    1. DB 事务内 create_run()                         │   │
│  │    2. db.commit()                                    │   │
│  │    3. enqueue_run() → actor.send(run_id) 入 Redis    │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  Redis（消息队列 + 心跳存储）                                 │
│  ┌──────────────┐  ┌──────────────┐                        │
│  │ critical 队列 │  │ default 队列 │                        │
│  └──────────────┘  └──────────────┘                        │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  Dramatiq Worker 进程（task-worker 容器）                     │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  AsyncIO middleware（EventLoopThread 跑 async actor）│   │
│  │  RunFailureMiddleware（失败兜底标 Run failed）        │   │
│  │  ReaperMiddleware（after_process_boot 启 Reaper 线程）│   │
│  │  ┌───────────────────────────────────────────────┐   │   │
│  │  │  process_run_default / process_run_critical   │   │   │
│  │  │    → execute_run_message(run_id)              │   │   │
│  │  │      → claim_run (CAS pending->running)       │   │   │
│  │  │      → start_worker_attempt (写 span)         │   │   │
│  │  │      → handler(ctx)                           │   │   │
│  │  │        → begin_span / end_span (span 心跳)    │   │   │
│  │  │        → commit_success (CAS running->succeeded)│  │   │
│  │  └───────────────────────────────────────────────┘   │   │
│  │  ┌───────────────────────────────────────────────┐   │   │
│  │  │  Reaper 线程（每 5min 扫卡死 Run）              │   │   │
│  │  └───────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  PostgreSQL（Run/Span 账本）                                 │
│  ┌─────────────────┐  ┌─────────────────┐                  │
│  │ processing_runs  │  │ processing_spans│                  │
│  └─────────────────┘  └─────────────────┘                  │
└─────────────────────────────────────────────────────────────┘
```

### 1.3 数据模型

**`processing_runs`**（Run 账本，业务权威状态）

| 字段 | 含义 |
|---|---|
| `id` / `public_id` | 内部 ID / 公开 UUID |
| `tenant_id` / `kb_id` | 租户 / KB 隔离 |
| `run_type` | `document_process` / `rag_index` / `source_sync` / `wiki_generate` |
| `scope_type` / `scope_id` | 处理目标类型与 ID（如 `revision` + revision_id）|
| `parent_run_id` | 编排链（如 `rag_index` 的 parent 是 `document_process`）|
| `attempt_no` | 业务重跑链中的序号（自动重试不递增）|
| `status` | `pending` / `running` / `succeeded` / `failed` / `cancelled` |
| `error_code` / `error_message` | 失败时的稳定错误码与摘要 |
| `started_at` / `finished_at` | 首次执行时间 / 终态时间 |
| `options_snapshot` | 实际生效的配置快照 |

**`processing_spans`**（Span 观测层，诊断流水）

| 字段 | 含义 |
|---|---|
| `run_id` / `attempt_no` / `span_name` | 唯一键（同一 Run 同一 attempt 的同一阶段）|
| `status` | `pending` / `running` / `succeeded` / `failed` / `skipped` / `cancelled` |
| `metrics` | 阶段指标 JSONB（如 `{"chunk_count": 5000}`）|
| `error_code` / `error_message` | 阶段失败诊断 |
| `started_at` / `finished_at` / `updated_at` | 时间戳；`updated_at` 作为心跳 |

---

## 2. 核心组件

### 2.1 `workers/core/constants.py`（常量与枚举）

集中管理所有业务常量，避免字符串字面量分散：

| 枚举/常量 | 说明 |
|---|---|
| `RunStatus` | `PENDING` / `RUNNING` / `SUCCEEDED` / `FAILED` / `CANCELLED` |
| `SpanStatus` | `PENDING` / `RUNNING` / `SUCCEEDED` / `FAILED` / `SKIPPED` / `CANCELLED` |
| `RunType` | `SOURCE_SYNC` / `DOCUMENT_PROCESS` / `RAG_INDEX` / `WIKI_GENERATE` |
| `ScopeType` | `SOURCE` / `REVISION` / `KNOWLEDGE_BASE` / `WIKI_PAGE` |
| `TriggerType` | `MANUAL` / `ON_INGEST` / `SYSTEM` / `SCHEDULE` / `RETRY` |
| `ErrorCode` | `ENQUEUE_FAILED` / `REAPER_RECOVERED` / `MIDDLEWARE_FAILURE` / `UNKNOWN_RUN_TYPE` / ... |
| `SpanName` | `WORKER_ATTEMPT` / `PARSE` / `PERSIST` / `EMBED` / `ACTIVATE` |
| `CRITICAL_QUEUE` / `DEFAULT_QUEUE` | 队列名 |
| `CRITICAL_RUN_TYPES` | `frozenset({RAG_INDEX, SOURCE_SYNC})`，走 critical 队列的 Run 类型 |

### 2.2 `workers/core/broker.py`（Broker 构造）

- 模块 import 时初始化 `RedisBroker` + `dramatiq.set_broker()`
- 注册 3 个 middleware：`AsyncIO` + `RunFailureMiddleware` + `ReaperMiddleware`

### 2.3 `workers/core/tasks.py`（Actor 注册与入队）

- **同函数多 actor 注册**（方案 C）：`process_run_default`（queue=default）+ `process_run_critical`（queue=critical）
- 两个 actor 共享同一份执行逻辑（`execute_run_message`），仅 `queue_name` 不同
- `enqueue_run(run_type, run_id)`：按 `run_type` 选 actor 入队（`CRITICAL_RUN_TYPES` 走 critical）
- `_load_handlers()`：延迟加载 handler 模块，避免循环 import

### 2.4 `workers/core/executor.py`（消息执行器）

`execute_run_message(run_id, *, worker_id, handlers, session_factory)`：

1. `claim_run`（CAS `pending->running`，重复投递被吸收）
2. `start_worker_attempt`（写 `worker_attempt` span）
3. 调 handler
4. handler 成功 → `commit_success`（CAS `running->succeeded`）
5. handler 抛 `TerminalTaskError` → `_handle_failure`（标 span failed + Run failed，不重试）
6. handler 抛其他异常 → `_handle_failure`（标 span failed + Run failed，Dramatiq Retries 接管重试）
7. `CancelledError`（time_limit 触发）→ 标 span cancelled，re-raise

### 2.5 `workers/core/runtime.py`（Run 状态机）

- `create_run`：事务内创建 Run 行（不写 Outbox）
- `claim_run`：CAS `pending->running`
- `complete_run`：CAS `running->succeeded`
- `fail_run`：CAS `running->failed`
- `mark_run_enqueue_failed`：CAS `pending->failed`（入队失败时）
- `start_worker_attempt` / `finish_worker_attempt`：写 `worker_attempt` span

### 2.6 `workers/core/span_tracker.py`（Span 心跳 API）

by-name shim + ctx pattern，对齐 WeKnora SpanTracker 4 事件：

| 函数 | 作用 | DB 操作 |
|---|---|---|
| `begin_span(ctx, name, *, input_summary)` | 开始阶段 span | INSERT（status=running）|
| `end_span(ctx, name, *, output_summary)` | 结束 span | UPDATE status=succeeded |
| `fail_span(ctx, name, *, error_code, error_message)` | 失败 span | UPDATE status=failed |
| `skip_span(ctx, name, *, reason)` | 跳过 span | UPDATE status=skipped |

- **唯一键**：`(run_id, attempt_no, span_name)`
- **best-effort**：DB 错误 log + swallow，不阻断业务
- **心跳**：每次操作刷 `spans.updated_at`

### 2.7 `workers/core/reaper.py`（卡死恢复）

- `recover_stalled_runs`：扫描两类卡死 Run 并标 failed
  - `running` 且 `started_at < span_cutoff` 且 (`MAX(spans.updated_at) < span_cutoff` 或无 running span)
  - `pending` 且 `created_at < pending_cutoff`
- `run_reaper_loop`：独立线程循环，每 `interval_seconds` 调一次 `recover_stalled_runs`

### 2.8 `workers/core/middleware.py`（Dramatiq middleware）

- `RunFailureMiddleware`：`after_process_message` 钩子，消息失败时用 `asyncio.run()` 调 `fail_run`（executor 兜底）
- `ReaperMiddleware`：`after_process_boot` 启 Reaper 线程，`before_worker_shutdown` 停止

---

## 3. 完整链路

以"上传文档 → 解析 → embedding"为例：

```
用户上传文档
    │
    ▼
[API 路由] upload_document(db, kb_id, user, filename, content)
    │
    ├─ 1. 上传 MinIO
    ├─ 2. create_document_process_run(db, ...)
    │      ├─ 创建 Document + DocumentRevision
    │      └─ create_run(db, run_type=DOCUMENT_PROCESS, scope_type=REVISION, ...)
    │         → Run 行 status=pending
    ├─ 3. db.commit()
    │      → Run 行落盘
    ├─ 4. enqueue_run(DOCUMENT_PROCESS, run.id)
    │      → process_run_default.send(run_id) 入 Redis default 队列
    │
    ▼
[Dramatiq Worker] process_run_default 消费消息
    │
    ├─ 5. execute_run_message(run_id, worker_id="default", ...)
    │      ├─ claim_run(run_id) → CAS pending->running
    │      ├─ start_worker_attempt → 写 worker_attempt span
    │      └─ 调 document_process_handler(ctx)
    │
    ▼
[document_process_handler]
    │
    ├─ 6. begin_span(ctx, PARSE)
    │      → 写 parse span (status=running)
    ├─ 7. 解析文档（parse_document + persist_parser_images）
    ├─ 8. 分块（chunk_text）
    ├─ 9. end_span(ctx, PARSE, output_summary={chunk_count})
    │      → UPDATE parse span status=succeeded
    │
    ├─ 10. begin_span(ctx, PERSIST)
    ├─ 11. commit_success(write_candidate_chunks)
    │       ├─ 写 ContentChunk 行
    │       ├─ 更新 DocumentRevision.status=ready
    │       ├─ create_run(db, run_type=RAG_INDEX, parent_run_id=...)
    │       │  → 子 Run 行 status=pending
    │       └─ complete_run(run_id) → CAS running->succeeded
    │       → 事务原子提交（业务结果 + Run 成功）
    ├─ 12. end_span(ctx, PERSIST)
    │
    ├─ 13. enqueue_run(RAG_INDEX, child_run_id)
    │       → process_run_critical.send(child_run_id) 入 Redis critical 队列
    │
    ▼
[Dramatiq Worker] process_run_critical 消费消息
    │
    ├─ 14. execute_run_message(child_run_id, worker_id="critical", ...)
    │      ├─ claim_run(child_run_id) → CAS pending->running
    │      └─ 调 rag_index_handler(ctx)
    │
    ▼
[rag_index_handler]
    │
    ├─ 15. begin_span(ctx, EMBED)
    ├─ 16. embed_texts([chunk.text for chunk in candidates])
    ├─ 17. end_span(ctx, EMBED, output_summary={embedded})
    │
    ├─ 18. begin_span(ctx, ACTIVATE)
    ├─ 19. commit_success(write_embeddings_and_activate)
    │       ├─ UPDATE content_chunks SET embedding=...
    │       ├─ 更新 DocumentRevision.status=ready
    │       ├─ 更新 Document.active_revision_id=...
    │       └─ complete_run(child_run_id) → CAS running->succeeded
    ├─ 20. end_span(ctx, ACTIVATE)
    │
    ▼
完成：文档已处理，可检索
```

---

## 4. 各种情况处理

### 4.1 正常流程

见第 3 节。Run 经历 `pending → running → succeeded`，每个阶段有 span 记录。

### 4.2 重复投递

**场景**：Dramatiq worker 处理消息时 ack 丢失（如 worker 崩溃后消息被重投）。

**处理**：
- `claim_run` 是 CAS `pending->running`
- 重复投递时 Run 已是 `running`（或终态），CAS 失败，返回 `False`
- `execute_run_message` 返回 `ExecutionOutcome.IGNORED`，消息正常 ack

**效果**：重复投递被吸收，不会重复执行 handler。

### 4.3 handler 瞬时错误

**场景**：handler 抛非 `TerminalTaskError`（如 embedding API 临时不可用）。

**处理**：
1. `execute_run_message` 的 `except Exception` 捕获
2. 包装为 `TransientTaskError(UNEXPECTED_EXCEPTION, str(exc))`
3. `_handle_failure`：标 span failed + Run failed
4. 异常冒泡给 Dramatiq
5. Dramatiq Retries middleware 按 `max_retries=3` + `min_backoff=5s` + `max_backoff=300s` 指数退避重试
6. 重试时 Dramatiq 用原 message enqueue，回到原队列
7. 重试时 `claim_run` 失败（Run 已 failed）→ 返回 `IGNORED`，消息 ack 丢弃

**注意**：当前实现中，`_handle_failure` 标 Run failed 后，重试消息会被 `claim_run` 吸收（Run 不是 pending）。这意味着**Dramatiq 的自动重试实际上不会重新执行 handler**。这是已知限制：用户需手动重试（创建新 Run）。

**后续优化**：Q1（handler 幂等策略调整）会改为"重试时重置 Run 为 pending"，让 Dramatiq 重试能真正重跑。

### 4.4 handler 终态错误

**场景**：handler 抛 `TerminalTaskError`（如 `empty_content` 文档无内容）。

**处理**：
1. `execute_run_message` 的 `except TerminalTaskError` 捕获
2. `_handle_failure`：标 span failed + Run failed
3. actor 装饰器 `throws=(TerminalTaskError,)`：Dramatiq 直接将消息标记为 failed（进死信），不重试

**效果**：终态错误不重试，Run 标 failed，用户可见。

### 4.5 handler 超时

**场景**：handler 执行超过 `time_limit=3600000ms`（1h）。

**处理**：
1. Dramatiq 向 actor 任务发送 `CancelledError`
2. `execute_run_message` 的 `except asyncio.CancelledError` 捕获
3. 标 span `cancelled`
4. re-raise `CancelledError`
5. Dramatiq 标记消息失败

**后续**：Run 仍是 `running` 状态（`_handle_failure` 未调用）。Reaper 70min 后扫到 span 心跳超时，标 Run failed。

### 4.6 worker 崩溃

**场景**：worker 进程崩溃（如 OOM、segfault）。

**处理**：
1. Dramatiq RedisBroker 的 `heartbeat_timeout=60s`：worker 进程崩溃后心跳停止
2. 60s 后，未 ack 的消息被 maintenance 过程放回队列
3. 其他 worker 进程消费该消息
4. `claim_run`：
   - 如果 Run 仍是 `pending`（崩溃前未 claim）→ claim 成功，正常执行
   - 如果 Run 是 `running`（崩溃前已 claim）→ CAS `pending->running` 失败，返回 `IGNORED`
5. Run 卡在 `running` → Reaper 70min 后扫到 span 心跳超时，标 failed

**恢复延迟**：约 5-10 分钟（Reaper 扫描间隔 + span 心跳超时）。

### 4.7 DB 提交后入队失败（双写窗口）

**场景**：`db.commit()` 成功，但 `enqueue_run()` 抛异常（如 Redis 故障）。

**处理**：
1. `enqueue_run` 异常冒泡给调用方
2. Run 卡在 `pending` 状态（DB 已提交，但消息未入队）
3. Reaper 5min 后扫到 `pending` 且 `created_at` 过旧，标 failed
4. 用户看到 Run failed，可手动重试

**已知限制**：接受这个不完美（spec §2.4 风险 3）。Reaper 5min 内 Run 看起来是 pending（用户可能困惑）。

**后续优化**：可在 `enqueue_run` 失败时调 `mark_run_enqueue_failed` 立即标 failed（当前未实现）。

### 4.8 长阶段执行

**场景**：embedding 5K chunks 耗时 15min。

**处理**：
- `TASK_SPAN_STALE_SECONDS=4200`（70min）>> 15min
- span 心跳阈值足够大，长阶段不会被 Reaper 误杀
- handler 不需要在长阶段内部刷新 span（粗粒度事件驱动）

**关键**：70min 阈值让最长的单阶段也能安全跑完。如果阈值是 5min，这个模型就崩了。

### 4.9 Dramatiq 重试

**场景**：handler 抛异常（非 TerminalTaskError）。

**处理**：
1. Dramatiq Retries middleware 捕获异常
2. 按 `max_retries=3` + `min_backoff=5000ms` + `max_backoff=300000ms` 计算延迟
3. 用原 message enqueue 到原队列（`queue_name` 是 frozen 字段，重试回原队列）
4. 延迟后重新消费

**注意**：见 4.3，当前实现中重试消息会被 `claim_run` 吸收（Run 已 failed）。Dramatiq 重试机制保留，但实际不重跑 handler。

### 4.10 死信

**场景**：
- handler 抛 `TerminalTaskError`（`throws` 配置）
- 或重试次数耗尽

**处理**：
- Dramatiq 将消息标记为 failed（`message.fail()`）
- 消息进入死信队列（Dramatiq 内部管理）
- Run 已被 `_handle_failure` 标 failed

**效果**：死信消息不再被消费，Run 状态清晰。

### 4.11 Reaper 兜底

**场景**：Run 卡在 `running` 或 `pending` 状态。

**扫描逻辑**（每 5min 一次）：

```
两类卡死 Run：
1. running 且 started_at < (now - 70min)
   且 (MAX(spans.updated_at) < (now - 70min) 或 无 running span)
   → span 心跳超时，worker 可能崩溃或卡死

2. pending 且 created_at < (now - 5min)
   → 入队失败或消息丢失
```

**动作**：
- 批量 UPDATE 标 failed（CAS `status IN (running, pending)` 防误杀已终态的 Run）
- `error_code = REAPER_RECOVERED`
- 不自动重投（用户手动重试）

**防误杀**：
- `started_at < span_cutoff` 避免杀刚 claim 但还没写 span 的 Run
- CAS `status IN (running, pending)` 避免杀已终态的 Run
- span 心跳只看 `status='running'` 的 span（已结束的 span 不影响心跳判断）

---

## 5. 配置参数

`backend/app/config/settings.py`：

| 参数 | 默认值 | 含义 |
|---|---|---|
| `TASK_WORKER_CONCURRENCY` | 16 | Worker 并发数（对应 `--threads 16`）|
| `TASK_PARSER_PROCESSES` | 2 | 解析进程数（保留，当前未用）|
| `TASK_MAX_AUTO_RETRIES` | 3 | Dramatiq actor `max_retries`（当前硬编码在 tasks.py）|
| `TASK_RETRY_BASE_SECONDS` | 5 | Dramatiq actor `min_backoff`（当前硬编码）|
| `TASK_RETRY_MAX_SECONDS` | 300 | Dramatiq actor `max_backoff`（当前硬编码）|
| `TASK_REAPER_INTERVAL_SECONDS` | 300 | Reaper 扫描间隔（5min）|
| `TASK_SPAN_STALE_SECONDS` | 4200 | Span 心跳超时阈值（70min）|
| `TASK_PENDING_STALE_SECONDS` | 300 | Pending Run 过旧阈值（5min）|
| `TASK_TIME_LIMIT_MS` | 3600000 | Dramatiq actor `time_limit`（1h）|

**阈值关系**：
- `TASK_TIME_LIMIT_MS`（1h）< `TASK_SPAN_STALE_SECONDS`（70min）：让 Dramatiq time_limit 先触发，Reaper 作为兜底
- `TASK_PENDING_STALE_SECONDS`（5min）<< `TASK_SPAN_STALE_SECONDS`（70min）：pending 快速检测，running 长阶段安全

---

## 6. 队列与路由

### 6.1 队列拓扑

| 队列 | 消费的 Run 类型 | 容量 |
|---|---|---|
| `critical` | `rag_index` / `source_sync` | 与 default 共享 worker 线程 |
| `default` | `document_process` / `wiki_generate` | 与 critical 共享 worker 线程 |

### 6.2 路由逻辑

`enqueue_run(run_type, run_id)`：

```python
if run_type in CRITICAL_RUN_TYPES:  # {RAG_INDEX, SOURCE_SYNC}
    process_run_critical.send(run_id)
else:
    process_run_default.send(run_id)
```

`queue_name_for_run(run_type)`（executor.py，用于诊断）：

```python
if run_type in CRITICAL_RUN_TYPES:
    return CRITICAL_QUEUE
return DEFAULT_QUEUE
```

### 6.3 同函数多 actor 注册（方案 C）

Dramatiq 的 `queue_name` 在 actor 定义时固定，不能 per-message 覆盖。因此用两个 actor 注册同一份执行逻辑：

```python
@dramatiq.actor(queue_name=DEFAULT_QUEUE, ...)
async def process_run_default(run_id): ...

@dramatiq.actor(queue_name=CRITICAL_QUEUE, ...)
async def process_run_critical(run_id): ...
```

两个 actor 内部都调 `execute_run_message`，仅 `queue_name` 不同。

### 6.4 重试路由

Dramatiq Retries middleware 重试时用原 message enqueue，`queue_name` 是 frozen 字段，重试回原队列。

---

## 7. 已知限制与后续优化

| 限制 | 影响 | 后续优化 |
|---|---|---|
| **Dramatiq 重试不重跑 handler** | `_handle_failure` 标 Run failed 后，重试消息被 `claim_run` 吸收 | Q1：handler 幂等策略调整，重试时重置 Run 为 pending |
| **双写窗口** | DB 提交后入队失败，Run 卡 pending 5min | 可在 `enqueue_run` 失败时调 `mark_run_enqueue_failed` |
| **`commit_success` 失败的边缘情况** | DB 临时故障导致 `complete_run` 失败，业务可能已部分写入 | 接受不完美（spec §2.4 风险 1）|
| **Dramatiq time_limit 与 span 心跳的交互** | worker 崩溃后 60s 重投，新 worker `claim_run` 失败，Run 卡 running 5-10min | 恢复延迟可接受 |
| **`max_retries` 等参数硬编码** | `tasks.py` 中 `max_retries=3` 等未从 settings 读取 | 后续可改为从 settings 读取 |

---

## 8. 参考文档

- `mydocs/specs/2026-08-05_00-00_Dramatiq任务队列迁移.md`（迁移 spec）
- `mydocs/dramatiq-migration-decision.md`（grilling 21 题决策记录）
- `mydocs/task-queue-comparison-weknora-vs-llm-wiki-agent.md`（WeKnora 对比分析）
- WeKnora 源码：`knowledge_housekeeping.go` / `knowledge_span_tracker.go`
- Dramatiq 文档：User Guide / Advanced Topics / Cookbook / API Reference
