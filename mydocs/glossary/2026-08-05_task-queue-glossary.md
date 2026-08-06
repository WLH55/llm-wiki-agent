# Glossary: 任务队列术语表

> 维护日期：2026-08-05
> 用途：Dramatiq 迁移过程中涉及的术语统一解释

---

## 队列与投递

### Transactional Outbox（事务性发件箱）
一种双写一致性模式：业务状态变更和消息投递意图在同一个 DB 事务中写入。独立的 Publisher 进程轮询 Outbox 表，将消息投递到消息队列。保证"业务提交成功 = 投递意图一定落库"。本项目已决策**删除**。

### at-least-once delivery（至少一次投递）
消息可能被投递一次或多次，消费者必须幂等。Dramatiq 和 Taskiq 都是这个语义。

### visibility timeout（可见性超时）
消息被取出后，如果在超时时间内未 ack，消息重新可见供其他消费者取。Dramatiq Redis broker 用 heartbeat_timeout（默认 60s）实现进程级崩溃重投。

### Dead Letter Queue / DLQ（死信队列）
重试耗尽或年龄超限的消息进入的队列，保留一定时间后自动删除。Dramatiq 内置 DLQ，保留 7 天。

---

## Fencing 与租约

### Fencing（ fencing token 机制）
防止僵尸/过期 Worker 提交写入的机制。本项目用 `execution_token + execution_epoch + lease_expires_at` 三件套。已决策**删除**，因为 handler 已有幂等检查。

### Lease（租约）
Worker 领取任务时获得的有限期执行权。 lease 过期意味着 Worker 可能已死。本项目已决策**删除 lease 字段**，改用 span 心跳判卡死。

### Heartbeat / 续租（Lease Renewal）
Worker 执行期间定期刷新 lease_expires_at，防止长任务被误判卡死。本项目已决策**删除续租**，改用 span 心跳（事件驱动）。

---

## Span 心跳

### Span 心跳（Span Heartbeat）
不是定时心跳，而是**事件驱动**的心跳。handler 在每个阶段切换时（begin/end）写 span 行，span 的 `updated_at` 被刷新。Reaper 扫描时读 `MAX(spans.updated_at)` 判断 Run 是否卡死。对齐 WeKnora 的 SpanTracker。

### SpanTracker
WeKnora 的 span 追踪器（`knowledge_span_tracker.go`），在 handler 各阶段调用 `BeginStage`/`EndSpan`/`FailSpan`/`SkipSpan`，每次都调 `touchKnowledgeHeartbeat` 刷新 `knowledge.updated_at`。

### Reaper（清扫器）
本项目简化版的"housekeeping"，嵌入 worker 进程，5min 扫一次。扫描两类卡死 Run：
1. running 且最近 span updated_at 超 70min 没动（worker 崩溃/卡死）
2. pending 且 updated_at 过旧（入队失败/崩溃丢消息）

动作：标 Run failed，不自动重投（对齐 WeKnora）。

---

## Dramatiq 特有

### Actor（演员）
Dramatiq 中被 `@dramatiq.actor` 装饰的函数，是异步任务的载体。每个 actor 绑定一个 `queue_name`（定义时固定，不能 per-message 覆盖）。

### Middleware（中间件）
Dramatiq 的扩展机制，提供生命周期钩子：
- `after_process_boot`：worker 子进程启动后（用于启动 Reaper）
- `after_process_message`：消息处理后（用于失败回调）
- `before_worker_shutdown`：worker 关闭前（用于停止 Reaper）

### EventLoopThread（事件循环线程）
Dramatiq AsyncIO middleware 创建的全局单例线程，跑一个 asyncio 事件循环。async actor 的协程被提交到这个事件循环执行。可被 Middleware 复用调 async 代码（`get_event_loop_thread().run_coroutine()`）。

### AsyncIO middleware
Dramatiq 的可选中间件，让 `async def` actor 可用。worker 线程调 async actor 时，协程提交到 EventLoopThread，worker 线程阻塞等结果，事件循环继续跑其他协程。并发协程数 = `--threads` 数。

### Retries middleware
Dramatiq 内置的重试中间件。重试时用原 message enqueue（queue_name 是 frozen 字段，重试回原队列）。支持 `max_retries` / `min_backoff` / `max_backoff` / `throws` / `retry_when`。

### heartbeat_timeout（心跳超时）
Dramatiq Redis broker 的进程级崩溃检测参数（默认 60s）。worker 进程崩溃后，心跳停止，60s 后未 ack 消息被放回队列。

### time_limit（时间限制）
Dramatiq actor 的执行时限（毫秒），超时抛 `TimeLimitExceeded`。本项目统一设 3600000（1h）。

---

## WeKnora 特有

### housekeeping
WeKnora 的孤儿任务清理器（`knowledge_housekeeping.go`），嵌入主进程的 cron，每 5 分钟扫一次。扫描 `parse_status IN ('processing','finalizing') AND updated_at < cutoff` 的 knowledge 行，阈值 70min。两道防误杀关卡：span 心跳 + 队列探针。动作：标 failed，不自动重投。

### fan-out（扇出）
一个编排任务派生出多个并行子任务。WeKnora 的 `knowledge:post_process` 是编排者，预写 `pending_subtasks_count` 计数，fan-out 所有富化子任务。每个子任务完成时原子递减计数，归零标记 completed。

### 富化（enrichment）
文档解析完成后对文本做进一步语义增强。WeKnora 四类：summary、question、graph、multimodal。

---

## 本项目特有

### Run（运行）
`processing_runs` 表的一行，代表一次可独立调度、可审计的业务处理。是业务账本和终态真相源。

### Span（阶段）
`processing_spans` 表的一行，代表 Run 内一个可观测阶段或单次 Worker 执行尝试。

### claim_run（领取 Run）
Worker 取到消息后，原子 CAS 把 Run 从 pending 改成 running。简化版只靠 `status` 字段，不依赖 token/epoch。重复投递时 CAS 失败，消息被 ack 丢弃。

### commit_success（提交成功）
Handler 执行完后，在同一个事务里写业务结果 + `complete_run`（CAS running->succeeded）。失败时抛异常，Dramatiq 重试。

### 方案 C（同函数多 actor 注册）
Dramatiq 的 queue_name 在 actor 定义时固定死。为实现多队列路由，用同一个函数装饰多次，每个绑定不同 queue_name 和 actor_name。重试时 Dramatiq 按 actor_name 路由回原队列。
