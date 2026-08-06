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
- 注册 3 个 middleware：`AsyncIO` + `RunFailureMiddleware`（`before=Retries` 注册，逆序链中在 Retries 之后执行，能读到 `message.failed` 最终判定）+ `ReaperMiddleware`

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
5. handler 抛 `TerminalTaskError` → 标 span failed + 异常冒泡（`throws` → DLQ，`RunFailureMiddleware` 标 Run failed，不重试）
6. handler 抛其他异常 → 标 span failed + `release_run`（回 pending）+ 异常冒泡（Dramatiq Retries 退避重试，重投消息再次 claim）
7. `CancelledError`（time_limit 触发）→ 标 span cancelled，re-raise

### 2.5 `workers/core/runtime.py`（Run 状态机）

- `create_run`：事务内创建 Run 行（不写 Outbox）
- `claim_run`：CAS `pending->running`
- `complete_run`：CAS `running->succeeded`
- `fail_run`：CAS `running->failed`（支持 `statuses` 参数，可同时覆盖 pending）
- `release_run`：CAS `running->pending`（瞬态失败后释放，供重试消息再领取）
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
  - `pending` 且 `updated_at < pending_cutoff`（未 claim 的 pending `updated_at≈created_at`，入队失败/丢失仍覆盖；release 后等待期不误杀）
- `run_reaper_loop`：独立线程循环，每 `interval_seconds` 调一次 `recover_stalled_runs`

### 2.8 `workers/core/middleware.py`（Dramatiq middleware）

- `RunFailureMiddleware`：`after_process_message` 钩子，仅当 `exception is not None and message.failed`（重试耗尽 / throws 终态错误）时标 Run failed；复用 EventLoopThread 的 loop 调 async（`get_event_loop_thread().run_coroutine()`，loop 不可用时退回 `asyncio.run()`）
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
3. 标 span failed + `release_run`（CAS running→pending，重试消息可再次领取）
4. 异常冒泡给 Dramatiq
5. Dramatiq Retries middleware 按 `max_retries=3` + `min_backoff=5s` + `max_backoff=300s` 指数退避重试
6. 重试时 Dramatiq 用原 message enqueue，回到原队列
7. 重试时 `claim_run` 成功（Run 已回 pending）→ 再次执行 handler

**注意**：2026-08-06 起已落地修复——executor 异常冒泡 + `release_run` 重置 pending，Dramatiq 自动重试会真正重跑 handler；消息最终死亡（重试耗尽/throws）时由 `RunFailureMiddleware` 标 Run failed。详见 `mydocs/specs/2026-08-06_14-17_Dramatiq重试死信落地.md`。

**后续优化**：Q1 剩余部分（handler 幂等策略调整，允许重做已完成步骤）仍待办；"重试时重置 Run 为 pending"（`release_run`）已落地。

### 4.4 handler 终态错误

**场景**：handler 抛 `TerminalTaskError`（如 `empty_content` 文档无内容）。

**处理**：
1. `execute_run_message` 的 `except TerminalTaskError` 捕获
2. 标 span failed + 异常冒泡（`throws` → DLQ，`RunFailureMiddleware` 标 Run failed）
3. actor 装饰器 `throws=(TerminalTaskError,)`：Dramatiq 直接将消息标记为 failed（进死信），不重试

**效果**：终态错误不重试，Run 标 failed，用户可见。

### 4.5 handler 超时

**场景**：handler 执行超过 `time_limit=3600000ms`（1h）。

**处理**：
1. Dramatiq 向 actor 任务发送 `CancelledError`
2. `execute_run_message` 的 `except asyncio.CancelledError` 捕获
3. 标 span `cancelled`
4. re-raise `CancelledError`
5. Dramatiq 对该消息调度一次重试（`CancelledError` 会被 Retries 计数）；重试消息被 `claim_run` 吸收后正常 ack，不会再次执行 handler

**后续**：Run 仍是 `running` 状态（executor 不标终态；Dramatiq 重试消息被 `claim_run` 吸收后正常 ack，不触发 `RunFailureMiddleware`）。Reaper 70min 后扫到 span 心跳超时，标 Run failed。

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

**恢复延迟**：约 70-75 分钟（span 心跳超时 70min + Reaper 扫描间隔 5min）。

### 4.7 DB 提交后入队失败（双写窗口）

**场景**：`db.commit()` 成功，但 `enqueue_run()` 抛异常（如 Redis 故障）。

**处理**：
1. `enqueue_run` 异常冒泡给调用方
2. Run 卡在 `pending` 状态（DB 已提交，但消息未入队）
3. Reaper 5min 后扫到 `pending` 且 `updated_at` 过旧，标 failed（该场景 Run 从未被 claim，`updated_at≈created_at`，行为不变）
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

**注意**：2026-08-06 起已落地修复——executor 异常冒泡 + `release_run` 重置 pending，重试会真正重跑 handler（见 4.3）。消息最终死亡时由 `RunFailureMiddleware` 标 Run failed（见 4.10）。

### 4.10 死信

**场景**：
- handler 抛 `TerminalTaskError`（`throws` 配置）
- 或重试次数耗尽

**处理**：
- Dramatiq 将消息标记为 failed（`message.fail()`）
- 消息进入死信队列（Dramatiq 内部管理）
- Run 由 `RunFailureMiddleware` 在消息最终死亡时标 failed（重试耗尽时 Run 处于 pending，`fail_run` 的 `statuses` 参数覆盖 running + pending）

**效果**：死信消息不再被消费，Run 状态清晰。

### 4.11 Reaper 兜底

**场景**：Run 卡在 `running` 或 `pending` 状态。

**扫描逻辑**（每 5min 一次）：

```
两类卡死 Run：
1. running 且 started_at < (now - 70min)
   且 (MAX(spans.updated_at) < (now - 70min) 或 无 running span)
   → span 心跳超时，worker 可能崩溃或卡死

2. pending 且 updated_at < (now - 5min)
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
| `TASK_REAPER_INTERVAL_SECONDS` | 300 | Reaper 扫描间隔（5min）|
| `TASK_SPAN_STALE_SECONDS` | 4200 | Span 心跳超时阈值（70min）|
| `TASK_PENDING_STALE_SECONDS` | 300 | Pending Run 过旧阈值（5min）|
| `TASK_TIME_LIMIT_MS` | 3600000 | Dramatiq actor `time_limit`（1h）|

> 注：`max_retries=3` / `min_backoff=5000` / `max_backoff=300000` 硬编码在 `tasks.py` 的 actor 装饰器（2026-08-06 已删对应 settings 死参数）；worker 并发由 `dramatiq --threads` 命令行控制。

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

（`queue_name_for_run` 已于 2026-08-06 死代码清理中删除，路由只保留 `enqueue_run` 一处。）

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
| ~~**Dramatiq 重试不重跑 handler**~~ | ~~异常被 executor 吞掉且 Run 已 failed，重试消息被 `claim_run` 吸收~~ | **已落地（2026-08-06）**：异常冒泡 + `release_run` 重置 pending + middleware 排序；Q1 剩余（handler 幂等）待办；Review 复核 PASS（2026-08-06，36/36）。详见 `mydocs/specs/2026-08-06_14-17_Dramatiq重试死信落地.md` |
| **双写窗口** | DB 提交后入队失败，Run 卡 pending 5min | 可在 `enqueue_run` 失败时调 `mark_run_enqueue_failed` |
| **`commit_success` 失败的边缘情况** | DB 临时故障导致 `complete_run` 失败，业务可能已部分写入 | 接受不完美（spec §2.4 风险 1）|
| **Dramatiq time_limit 与 span 心跳的交互** | worker 崩溃后 60s 重投，新 worker `claim_run` 失败，Run 卡 running 5-10min | 恢复延迟可接受 |
| **`max_retries` 等参数硬编码** | `tasks.py` 中 `max_retries=3` 等未从 settings 读取（对应 settings 死参数已删）| 后续可改为从 settings 读取 |

---

## 8. FAQ：会话答疑记录（2026-08-06）

> 本会话中逐条提出的疑惑与解答汇总（Q/A 形式），按主题分组。正文（§1–§7）为准；本 FAQ 仅作答疑速查，若与正文冲突以正文为准。代码引用均为 2026-08-06 现状。

### 8.1 框架原理：退避 / 重试 / 死信（Redis 底层）

**Q1：`compute_backoff`（min 5s → max 300s + jitter）的原理是什么？**

公式（`dramatiq/common.py`）：

```python
exponent = min(attempts, 32)                          # 指数封顶 32
backoff  = min(factor * 2 ** exponent, max_backoff)   # factor=min_backoff(ms)
if jitter:                                            # jitter=True（默认）
    backoff = int(backoff / 2 + uniform(0, backoff / 2))  # 落在 [nominal/2, nominal]
```

本项目 `min_backoff=5000, max_backoff=300000`（`tasks.py` actor 装饰器硬编码）→ 第 1/2/3 次重试等待分别 **5–10s / 10–20s / 20–40s**，指数增长到 300s 封顶。调用点：`Retries.after_process_message`（`dramatiq/middleware/retries.py`）算出 delay 后 `broker.enqueue(message, delay=delay)`。

**Q2：用的 Redis 什么数据类型？有没有专门的"延时 / 重试 / 死信"结构？**

没有专门结构，是 **5 类普通键 + 一个 Lua 脚本**（`dramatiq/brokers/redis/dispatch.lua`）拼出的投递协议；enqueue/fetch/ack/nack/requeue/purge 每个命令都是 Lua 原子执行：

| 键（namespace=dramatiq, queue=default） | 类型 | 作用 |
|---|---|---|
| `dramatiq:default` | List | 待处理消息 id，RPUSH 入队 / LPOP 取出 |
| `dramatiq:default.msgs` | Hash | message_id → 消息体 JSON（retries / eta / traceback 都在里面） |
| `dramatiq:__acks__.<worker_id>.default` | Set | 已取出未 ack 的消息 id = 在途租约（at-least-once 关键） |
| `dramatiq:__heartbeats__` | ZSet | worker_id → 最后心跳时间戳（每次任意 dispatch 顺带 ZADD） |
| `dramatiq:default.DQ` + `.msgs` | List + Hash | 延迟消息停车位 |
| `dramatiq:default.XQ` + `.XQ.msgs` | ZSet + Hash | 死信：ZSet 按死信时间排序，Hash 存消息体 |

**Q3：延迟消息在 Redis 里怎么存？"到点投递"谁计时？**

`enqueue(delay)`（`brokers/redis.py`）会**复制消息**、生成新 `redis_message_id`（UUID；源码注释：原 message_id 重试时不安全）、队列名改成 `default.DQ`、`options` 写 `eta = now + delay`，然后 HSET + RPUSH 进 DQ。worker 启动时为每个 `.DQ` 单独开消费者线程（prefetch 放大到 `worker_threads*1000`），把带 eta 的消息立刻取走放进**进程内 PriorityQueue**（`worker.py` 的 `handle_message` / `handle_delayed_messages`），eta 到点后去掉 `.DQ` 后缀、删 eta、重新 enqueue 回主队列（又一个新 redis_message_id），再 ack 掉 DQ 旧记录。

> 关键：**Redis 的 DQ 只是持久停车位，倒计时在 worker 进程内存里**。worker 全挂时消息停在 DQ List，eta 在消息体内不丢；重启后 DQ 消费者继续按 eta 回主队列。

**Q4：死信（DLQ 7 天）怎么实现？有没有定时器？**

触发：命中 `throws=(TerminalTaskError,)` 或 `retries >= max_retries` → `message.fail()`（只设 `MessageProxy.failed=True`）→ worker `post_process_message` 走 nack → Lua `nack`：SREM 租约 + ZADD `default.XQ`(score=now) + HSET `default.XQ.msgs` + HDEL `default.msgs`。死信消息只存在于 XQ。

7 天 TTL = `DEFAULT_DEAD_MESSAGE_TTL = 86400000*7`（`brokers/redis.py`）。**没有独立定时器**：每次任意 dispatch 命令有 `1000/1_000_000` 概率触发惰性维护（`_should_do_maintenance`，ack/nack 黑名单除外），维护里 `ZRANGEBYSCORE XQ 0 now-7d` → ZREM + HDEL 清过期死信。

**Q5：worker 崩溃后"谁把消息捞回来"？**

同一段惰性维护：`ZRANGEBYSCORE __heartbeats__ 0 now-heartbeat_timeout(60s)` 找心跳超时的 worker → `SMEMBERS` 它的 acks 组 → 对仍在 msgs hash 里的消息 id `RPUSH` 回队列 → 清理 acks 组与心跳。所以"崩溃重投"不是定时器，而是下一次任意 Redis 操作随机触发。

### 8.2 span 心跳与 worker_attempt

**Q6：`spans.updated_at` 作为心跳是什么意思？怎么判断卡死？**

心跳 = "这个时间戳还在被刷新" = 执行还活着，不是主动发信号。`begin_span` / `end_span` / `fail_span` 每次 UPDATE 都会刷 `updated_at`。Reaper 判死逻辑（`reaper.py`）：`running` 状态 Run 且 `started_at < now-70min` 且（`MAX(running span 的 updated_at) < now-70min` 或无 running span）→ 认为心跳断了。**扫描的是 `processing_runs` 表，子查询 join `processing_spans` 表**（`MAX(spans.updated_at)` 只看 `status='running'` 的 span，已结束的 span 不影响心跳判断）。

**Q7：完整例子（14:00:05–14:00:10）？心跳到底看哪条记录的时间？**

一次执行（假设已有 500/501/502/503 号 span）：
- 14:00:05–14:00:06：running 的 span 只有 501（worker_attempt）→ 它是唯一心跳源，MAX = 501 的 updated_at
- 14:00:06–14:00:09：running 集合 = 501 + 502（parse 开始），MAX(updated_at) 一直新鲜
- 14:00:09–14:00:10：parse 结束（不再 running），running = 501 + 503（persist），心跳继续刷新
- 若之后 persist 也不再刷新：running 集合只剩 501，心跳时间 = 501 的 updated_at，70min 不再动 → Reaper 判死

**判断的是"该 run_id 的 running span 集合里最新更新的那一条"，不是某一条固定记录**；14:00:11.5 之后若业务 span 全结束，心跳自然回到 worker_attempt 的时间。

**Q8：worker_attempt 为什么要额外插入？其他业务 span 不也有 attempt_no 吗？**

业务 span（parse/persist/embed/activate）只覆盖 handler 内部阶段；worker_attempt（`start_worker_attempt` 在 handler 调用前写）覆盖**整个消息执行外壳**：claim 之后、handler 之前、异常收尾。它保证任何时刻至少有一个 running span 当心跳源——即使 handler 还没来得及写任何业务 span（如 claim 后立刻崩溃），worker_attempt 的 updated_at 也是新鲜的。attempt_no 是两者共有的关联键（业务 span 对齐同一轮执行），不是替代关系：worker_attempt 是"外壳"，业务 span 是"外壳内的阶段"。

**Q9：executor 把 worker_attempt 标成 `cancelled` 是什么意思？cancelled 状态业务 span 没有？**

业务 span 状态只有 running / succeeded / failed / skipped；worker_attempt 额外支持 `cancelled`（`executor.py` 捕获 `asyncio.CancelledError` 时 `finish_worker_attempt(status=CANCELLED)`，即 Dramatiq time_limit 触发）。含义："这次消息执行被框架中断"，与业务失败区分开。两者**都在 `processing_spans` 表里**，只是 worker_attempt 多一个状态值 + 特定 span_name。

**Q10：`COUNT(已有 worker_attempt) + 1` 是干嘛的？**

`start_worker_attempt`（`runtime.py`）统计该 run 已有 WORKER_ATTEMPT span 数量 +1 作为本次 `attempt_no`：首次执行=1、第一次重试=2……让 `(run_id, attempt_no)` 唯一标识一次执行，重试的诊断记录不互相覆盖。并发安全由 `claim_run` CAS 保证——同一时刻只有一条消息能进入 running，COUNT+1 不会撞号。

**Q11：业务都完成了，但 `finish_worker_attempt` 没收尾会怎样？**

worker_attempt 保持 running：
- Run 已终态（succeeded/failed）→ Reaper 的 CAS `status IN (running, pending)` 不会动它，只是残留一条悬挂的 running span（数据脏，可接受；`finish_worker_attempt` 自带 `WHERE status='running'`，不会被二次覆盖）
- Run 未终态且后续没人刷它 → 心跳 70min 断 → Reaper 兜底标 failed

### 8.3 CAS 与吸收重复投递

**Q12：`claim_run` 的 CAS `pending->running` 吸收重复投递是什么意思？CAS 怎么操作？**

"重复投递"= 同一条消息可能被投递多次：worker 崩溃 60s 后重投、重试消息重投。`claim_run`（`runtime.py`）就是带 WHERE 条件的 UPDATE：

```sql
UPDATE processing_runs SET status='running', started_at=..., updated_at=...
WHERE id=:run_id AND status='pending'
```

`rowcount=0` 说明 Run 已被别人领走或已终态 → 返回 False → executor 直接返回 `IGNORED`，**不跑 handler**。这条重复消息就被"吸收"（吞掉）：消息正常 ack，业务零副作用。数据库行锁保证原子，不需要分布式锁。

**Q13：批量 UPDATE 带 `status IN (running, pending)` 的 CAS 保护（`reaper.py`）防误杀，举例？**

Reaper 扫到疑似卡死 Run 后标 failed 时：`UPDATE ... WHERE id IN (...) AND status IN ('running','pending')`。例子：Reaper 查出 run42 心跳超时、正要标 failed 的同一瞬间，最后一次重试消息刚好执行成功、`complete_run` 把 run42 标成 succeeded → CAS 条件不满足、rowcount=0 → **成功结果保住**。没有这个 CAS，succeeded 会被覆盖成 failed（用户看到"失败"，实际数据已写好）。

### 8.4 Reaper 与判死阈值

**Q14：Reaper 兜底是干嘛的？扫描哪个表？**

兜住"没有任何正常路径收尾"的卡死：worker 崩溃前已 claim（消息重投被吸收、无人标终态）、time_limit 取消后重投被吸收等。独立线程嵌入 worker（`ReaperMiddleware.after_process_boot` 启动），每 5min 扫一次，标 failed + `REAPER_RECOVERED`，不自动重投（用户手动重试）。扫描 `processing_runs`（join `processing_spans` 心跳），两类：running 心跳超 70min；pending 过 5min。

**Q15：现在项目设置了哪些时间？各有什么用？**

| 参数 | 值 | 作用 |
|---|---|---|
| `TASK_TIME_LIMIT_MS` | 3600000（1h） | Dramatiq actor time_limit：单条消息执行硬上限，超时发 CancelledError 取消 actor 并调度重试 |
| `TASK_SPAN_STALE_SECONDS` | 4200（70min） | Reaper 判死：running span 心跳超 70min → 认为卡死 |
| `TASK_PENDING_STALE_SECONDS` | 300（5min） | Reaper 判死：pending 过 5min → 入队失败 / 消息丢失 |
| `TASK_REAPER_INTERVAL_SECONDS` | 300（5min） | Reaper 扫描间隔 |
| `max_retries=3 / min_backoff=5000 / max_backoff=300000` | tasks.py 硬编码 | 重试次数与退避区间 |
| heartbeat_timeout=60s | Dramatiq 默认 | worker 崩溃判定，之后未 ack 消息被捞回队列 |
| 死信 TTL 7 天 | Dramatiq 默认 | 死信保留时间，惰性维护清理 |

**Q16：time_limit 60min 已取消，为什么还要 70min 判死阈值？**

两者职责不同：60min 是**框架对单条消息执行**的硬上限（到点取消 actor）；70min 是**业务状态判死**阈值。time_limit 触发后重试消息大概率被 `claim_run` 吸收（Run 还是 running），之后没有任何消息在跑 → 没有任何路径标终态 → 只能靠 Reaper 70min 兜底。60 < 70 保证 time_limit 先触发、Reaper 永远只是兜底，且 70min 给"取消后的重试窗口 + 正常长阶段"留了余量。

### 8.5 崩溃恢复与用户感知

**Q17：崩溃前已 claim（Run=running）→ 重投被吸收 → 用户要等 70min 才看到失败吗？**

是的。这条链路上没有任何代码能立即标失败：重投消息 claim 失败返回 IGNORED、正常 ack，不触发异常、不触发 RunFailureMiddleware；executor 不标终态。只能等 Reaper 70min 兜底（恢复延迟约 70–75min）。

**Q18：为什么不等 Reaper，改为"吸收时立即 fail_run"？要干嘛？有什么风险？**

目的：把用户感知从 70min 压到 1–2min。做法：claim_run 返回 IGNORED 且判定为"崩溃重投"时直接 fail_run（约 30 行 + 测试）。风险：
- 需要区分"崩溃重投"和"time_limit 重试被吸收"——前者 handler 一定已死；后者 handler 可能刚被取消/还在收尾，立即标 failed 可能与真实执行竞争（竞态窗口内 commit_success 会被 CAS 挡住，可能误标）
- 消息里没有显式"崩溃"标记，只能靠 eta / 重试次数等推断，有误判面
- 与 Reaper 双兜底的关系要重新理清（谁先谁后、幂等性）
- **结论（2026-08-06）：暂不实施**，先只加 `docker-compose.yml` 的 `restart: unless-stopped` 降低崩溃概率本身；如需快速感知再按此方案做。

**Q19：WeKnora-feat_MCP 怎么处理这类问题？**

已单独调研，结论见 `mydocs/task-queue-comparison-weknora-vs-llm-wiki-agent.md`（本设计借鉴其 housekeeping + span 心跳兜底哲学）。

### 8.6 清理与决策记录

**Q20：历史遗留死代码 / 死参数清理了哪些？**

2026-08-06 清理：settings 中 `max_retries / min_backoff / max_backoff` 等死参数（实际由 tasks.py actor 装饰器硬编码）、`queue_name_for_run` 死路由（只保留 `enqueue_run` 一处）、Reaper 相关未用参数等。清理记录已同步到本文档 §5 注、§6.2 注；重试死信落地 spec 见 `mydocs/specs/2026-08-06_14-17_Dramatiq重试死信落地.md`。

**Q21：docker-compose 改了啥？**

`task-worker` 服务加 `restart: unless-stopped`（`docker-compose.yml`，容器退出自动拉起，减少"worker 挂了没人管"的窗口）。**只加这一项**，其余（如 Q18 的"吸收时立即 fail_run"）暂不实施。

**Q22：现在设计与旧文档《任务运行时三表设计与消息队列原理详解》的覆盖关系？**

旧文档是 Taskiq + Redis Stream + Transactional Outbox 旧设计（含 task_outbox、fencing、租约续租、Outbox Publisher、四条 Stream），2026-08-05 已迁移。功能对照（旧 → 新）：

| 旧设计功能 | 现设计对应 |
|---|---|
| 双写原子性（Outbox） | 无 Outbox，接受双写窗口，Reaper pending 5min 兜底（§4.7） |
| 消息丢失防护 | 同上，pending 兜底 |
| 重复投递去重（claim 原子 CAS） | `claim_run` CAS（思路保留，旧文档 §9） |
| 僵尸消费者 fencing（token/epoch/lease） | 删除，靠 claim_run CAS 吸收重复投递 |
| 消费者卡死恢复（Reaper） | span 心跳 + Reaper（逻辑迁移，扫描字段换成 spans.updated_at） |
| 两层重试 | Dramatiq Retries（第一层）+ 用户手动重试（第二层），`release_run` 回 pending |
| 毒消息 / 死信 | throws + Retries 耗尽 → DLQ + RunFailureMiddleware 标终态 |
| 延迟投递 | Dramatiq DQ（eta + worker 内存 PriorityQueue） |
| 投递确认（ack） | Dramatiq acks Set（Redis 层，dispatch.lua） |
| 可观测性 | spans 表保留（worker_attempt + 业务 span） |
| 背压 / 优先级 | Dramatiq prefetch + critical / default 队列分离 |

---

## 9. 参考文档

- `mydocs/specs/2026-08-05_00-00_Dramatiq任务队列迁移.md`（迁移 spec）
- `mydocs/dramatiq-migration-decision.md`（grilling 21 题决策记录）
- `mydocs/task-queue-comparison-weknora-vs-llm-wiki-agent.md`（WeKnora 对比分析）
- WeKnora 源码：`knowledge_housekeeping.go` / `knowledge_span_tracker.go`
- Dramatiq 文档：User Guide / Advanced Topics / Cookbook / API Reference
**Review 复核（2026-08-06）**：语义落地复核 PASS——瞬态失败期间 Run 回 pending（任务状态显示 pending），重试耗尽/throws 时标 Run failed；核心 3 文件 36/36 + ruff clean。详见新 spec §6。
