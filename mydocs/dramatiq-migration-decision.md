# Dramatiq 迁移调研决策记录

> 整理日期：2026-08-04
>
> 背景：在 WeKnora 对比分析（见 `task-queue-comparison-weknora-vs-llm-wiki-agent.md`）后，调研是否将当前 Taskiq + Outbox 自建投递层迁移到 Dramatiq 框架。
>
> 约束：借鉴 WeKnora 设计哲学（成熟框架兜底投递复杂度），不想提前过度设计。

---

## 1. 决策结论总览

| 决策项 | 结论 | 理由 |
|---|---|---|
| 通用 Outbox | **删除** | WeKnora 验证"直接入队 + 恢复扫描"够用；任务均可重试可重建，非金融级不可丢 |
| 投递框架 | **换 Dramatiq + Redis** | Taskiq 投递能力不全，Dramatiq 内置重试/死信/延迟/崩溃重投，砍掉自建件 |
| Fencing | **删除**（token/epoch/lease 全删，改用 span 心跳判卡死）| handler 已有幂等检查挡重复写入，fencing CAS 是冗余；span 心跳对齐 WeKnora，更优雅 |
| 业务账本 | **保留** `processing_runs` / `processing_spans` | 业务审计必需，Dramatiq 不替代 |
| 并发模型 | 单进程多线程（`--threads 16`） | 全部任务是 IO 密集，多线程与多协程并发能力等价 |
| Worker 容器拓扑 | **单容器订阅 critical + default** | 先启动一个进程，`dramatiq --queues critical default --threads 16`；Reaper 嵌入此进程 |
| 多队列路由 | **方案 C：同函数多 actor 注册** | Dramatiq 的 queue_name 在 actor 定义时固定死，不能 per-message 动态覆盖（源码验证）|
| 弹性借用 | **放弃** | Dramatiq 多队列订阅是平级消费，不是"default 空闲时借 critical"；low 和 default 共享 worker |
| multimodal 队列 | **删除** | 当前 `queue_name_for_run` 未映射 multimodal，实际未使用 |
| low 队列 | **删除** | 当前只给 `wiki_generate` 用，非高频任务，不值得单独隔离；wiki_generate 改到 default |
| 消息内容 | **只传 run_id** | worker 回 DB 读 Run 快照；和 WeKnora 传 payload 不同，因为要回 DB 做幂等检查 |
| 重试队列路由 | **Dramatiq 自动回原队列** | Retries middleware 用原 message enqueue，queue_name 是 frozen 字段，重试回原队列（源码验证）|
| lease 时长 | **删除 lease 字段** | 改用 span 心跳判卡死，不再需要 lease |
| Reaper 触发方式 | **嵌入 worker 进程，5min 扫一次** | WeKnora housekeeping 也是嵌入主进程的 cron，5 分钟扫一次；SKIP LOCKED 防多 worker 重复 |
| Reaper 判定依据 | **span 心跳**（running 且最近 span updated_at 超 5min 没动）| 对齐 WeKnora；span 心跳是事件驱动（阶段切换时刷新），不是定时心跳 |
| Reaper 动作 | **标 Run failed，不自动重投** | 对齐 WeKnora；lease 过期通常意味着异常崩溃，自动重做有再次崩溃风险且浪费 API 调用；用户手动重试 |
| 失败回调 | **自定义 Middleware（方案 A）** | 对齐 WeKnora 的 asynq 死信中间件 + 回调；在 `after_process_message` 钩子标 Run failed |
| Actor 模式 | **路径 C：actor 是薄包装，保留 executor** | `execute_run_message` 保留 claim/handler 派发/commit；删退避/心跳/retry_run（交给 Dramatiq）|
| claim 失败处理 | actor 正常返回，Dramatiq ack 消息 | 重复投递被吸收，不触发重试 |

---

## 2. 关键问题澄清记录

### 2.1 概念澄清：WeKnora 文档中的若干术语

来源：`task-queue-comparison-weknora-vs-llm-wiki-agent.md` 调研时的疑问。

#### fan-out 所有富化子任务

**fan-out（扇出）**：分布式系统术语，指一个编排任务"散开"派生出多个并行子任务，像扇子展开从一个点辐射到多个点。

**富化（enrichment）**：文档解析完成后对文本做进一步语义增强处理。WeKnora 的富化子任务四类：

| 富化类型 | 队列 | 粒度 |
|---|---|---|
| `summary:generation` / `datatable:summary` | summary | 整篇 1 个 |
| `question:generation` | question | 按 chunk 分批 |
| `chunk:extract` | graph | 每 chunk 一个 |
| `image:multimodal` | multimodal | 每张图一个 |

具体动作：文档解析完成后入队 `knowledge:post_process`，它作为编排者，预写 `pending_subtasks_count` 计数，然后一次性把这些富化任务并行派发到各条队列。每个子任务完成时原子递减计数，归零才标记 knowledge 为 completed。

对比：llm-wiki-agent 用 `parent_run_id` 树状编排表达依赖，WeKnora 用"计数"方式。

#### 启动重建 wiki 触发器 + Lite 模式重置孤儿 + housekeeping

这是 WeKnora 崩溃恢复的三种机制，对应不同场景：

- **启动重建 wiki 触发器**：启动时 `recover_pending_wiki_tasks` 从 PostgreSQL 的 `task_pending_ops` 表按 KB 重建 Redis 里的 wiki debounce 触发器。wiki 用了"迷你 Outbox"，意图已落库，Redis 触发器丢了可重建。
- **Lite 模式重置孤儿**：单机无 Redis 模式下，启动时 `reset_pending_tasks` 把卡住的孤儿任务行直接重置为 failed（单机不会有人还在跑）。
- **housekeeping**：分布式模式下的孤儿任务清理器。比 `reset_pending_tasks` 谨慎：同时检查 `knowledge_processing_spans`（阶段流水）是否有活动 span + 真实 asynq Redis 队列里任务是否还在，两边都确认没人执行才重置，避免误杀正在运行的副本。

### 2.2 Dramatiq 与 FastAPI 适配性

**结论：适配，无摩擦。**

- **进程分离天然兼容**：FastAPI 进程负责 API + 入队（`actor.send()`），Dramatiq worker 进程负责消费。两进程共享同一份 actor 模块代码。
- **入队侧零摩擦**：FastAPI 的同步/异步 handler 里都可以直接调用 `actor.send()`（同步操作，把消息推给 Redis）。当前 Taskiq 的 `.kicker().with_labels().kiq()` 换成 `actor.send()` 更简单。
- **Django/Flask 有官方集成库，FastAPI 不需要**：集成库做的事是"配置加载 + app factory 适配"，FastAPI 配置自己管（`app/config.py`），模块顶层 `dramatiq.set_broker(redis_broker)` 即可。
- **关键约束**：async actor 需要加 `AsyncIO` middleware（见 2.3）。

### 2.3 并发模型：Dramatiq 的 AsyncIO middleware 真实工作方式

**核心结论：Dramatiq + AsyncIO 的并发能力和 Taskiq 等价，不是"退化"。**

#### 源码证据（`dramatiq/asyncio.py` 的 `EventLoopThread.run_coroutine`）

```python
def run_coroutine(self, coro):
    future = asyncio.run_coroutine_threadsafe(wrapped_coro(), self.loop)
    # worker 线程在这里阻塞等待，但事件循环继续转
    return future.result(timeout=self.interrupt_check_ival)
```

执行流程：
1. 每个 worker 进程只有 1 个事件循环线程（`EventLoopThread` 是全局单例）
2. worker 线程（默认 8 个）从队列取消息，调用 async actor 时，`async_to_sync` 把协程提交到那个唯一的事件循环，worker 线程自己阻塞等结果
3. `run_coroutine_threadsafe` 是非阻塞提交，worker 线程阻塞了，但事件循环没阻塞，继续跑其他已提交的协程

**所以当 8 个 worker 线程各自取了一条消息**：8 个协程都被提交到同一个事件循环，这 8 个协程在事件循环里并发执行（IO 等待时互相让出），8 个 worker 线程各自阻塞等自己的协程完成。**不是串行，是并发。**

#### 对比表

| | Taskiq 当前 | Dramatiq + AsyncIO |
|---|---|---|
| 事件循环数 | 1 | 1 |
| 并发协程数 | 14（`--max-async-tasks 14`）| = `--threads` 数 |
| 控制方式 | 直接控制协程数 | 通过线程数间接控制 |
| 多出来的开销 | 无 | N 个 worker 线程的栈和切换开销（约 8MB × N） |

#### 纠正记录

调研中曾误判为"退化"，经源码查证后纠正：并发能力完全一样，都是"1 个事件循环 + N 个并发协程"。Dramatiq 多了一层"worker 线程提交协程再阻塞等"的间接层，多了线程开销，但协程并发数相等。

### 2.4 Python 并发基础：IO 密集 vs CPU 密集

#### IO 密集型：多线程 vs 多协程

**并发能力基本相等**，区别在资源开销和调度方式：

| 维度 | 多线程 | 多协程 |
|---|---|---|
| 并发数上限 | 几百（线程栈约 8MB × N，吃内存）| 几万（协程栈 KB 级）|
| 调度 | OS 抢占式，线程切换有内核开销 | 事件循环协作式，切换在用户态 |
| IO 等待时 | GIL 释放，其他线程能跑 | `await` 让出，事件循环跑别的协程 |

**关键**：IO 等待期间 GIL 会释放，所以多线程在 IO 密集场景能真正并发，不是 GIL 卡死。

#### CPU 密集型：多线程 vs 多协程 vs 多进程

| 方式 | 能并行吗 | 原因 |
|---|---|---|
| 多线程 | ❌ 不能 | GIL 让同进程内线程无法同时执行 Python 字节码，CPU 密集任务线程间互相抢 GIL，实际串行 |
| 多协程 | ❌ 不能 | 协程在单线程单事件循环里，本质串行，`await` 只在 IO 时让出，CPU 计算不让出 |
| 多进程 | ✅ 能 | 每个进程独立 GIL，真正并行 |

#### 本项目的任务分类

经查证（`app/integrations/embedding.py` + `settings.py`）：

| 任务 | 类型 | 证据 |
|---|---|---|
| 文档解析（DocReader）| IO | 调远端解析服务 / 读文件 |
| 分块 | CPU 轻量 | 正则切分，耗时可忽略 |
| Embedding | **IO** | 调 Jina API（`client.embeddings.create`），非本地模型 |
| LLM 生成（wiki/summary）| IO | 调 LLM API |
| 向量写入 PG | IO | DB 写入 |

**结论：全部任务是 IO 密集，没有重 CPU 任务**。多线程与多协程并发能力等价，换 Dramatiq 不损失并发能力。

---

## 3. 六项可靠性保证的迁移对照

### 3.1 重试

**当前实现**（`executor.py:160-211` + `runtime.py:291-330`）：
- `_handle_failure` 算退避（base=5s, max=300s, 指数 + jitter）
- `retry_run` 把 Run 回退 pending + 写一条新 Outbox（延迟 `available_at`）
- `max_auto_retries=3`，超过转 `fail_run` 终态
- 错误分类：`TransientTaskError`（可重试）vs `TerminalTaskError`（直接失败）

**Dramatiq 对应**：
```python
@dramatiq.actor(max_retries=3, min_backoff=5000, max_backoff=300000)
async def process_run(run_id: int): ...
```
- 内置指数退避 + jitter，参数与当前完全对齐
- `throws=(TerminalTaskError,)` 让终态错误不重试
- `retry_when` 回调可替代 `TransientTaskError` 判定

**迁移结论**：`executor.py` 的 `_retry_delay` / `_handle_failure` 退避计算逻辑**可删**，`runtime.py` 的 `retry_run` **可删**，交给 Dramatiq。错误分类保留（`throws` 用）。

### 3.2 死信

**当前实现**：没有独立死信表。重试耗尽后 `fail_run` 把 Run 置为 `failed` + 写 `error_code` / `error_message`，错误落在 Run/Span 终态。

**Dramatiq 对应**：内置 Dead Letter Mailbox，重试/年龄超限的消息自动进 DLQ，保留 7 天，可手动检查、重新入队。

**迁移结论**：Dramatiq 的 DLQ 是额外赠送的能力，不丢任何东西。Run 终态记录（`error_code`/`error_message`）仍保留在 `processing_runs` 表里。

### 3.3 崩溃重投

**当前实现**（`reaper.py`）：
- 每 30s 扫描 `pending` 且创建时间过旧 / `running` 且 lease 过期的 Run
- 条件：该 Run 没有未发布的 Outbox
- 动作：补写一条 Outbox，触发重新投递

**Dramatiq 对应**：
- Redis broker 有 visibility timeout（默认 1 小时，可配）：消息被取出后若未 ack，超时自动重新可见
- worker 进程崩溃 -> 消息未 ack -> visibility timeout 后自动重投

**迁移结论**：`reaper.py` 的 Outbox 补投逻辑**可删**。但有边界场景需要保留简化版 Reaper：
- worker 取了消息、claim_run 成功、开始执行，然后崩溃 -> Dramatiq 会重投消息 -> 新 worker 调 `claim_run` 发现 Run 是 `running` 且 lease 未过期，返回 None，消息被忽略 -> **任务卡住直到 lease 过期**
- **解法**：保留简化版 Reaper，只扫"running 且 lease 过期"的 Run，重新 `actor.send(run_id)`。比当前 Reaper 简单（不用查 Outbox，直接 send）。

### 3.4 延迟

**当前实现**（`runtime.py` 的 `retry_run`）：`available_at = now + delay`，写进 Outbox，Publisher 轮询时 `WHERE available_at <= now` 才领取。

**Dramatiq 对应**：
```python
process_run.send_with_options(args=(run_id,), delay=5000)  # 5 秒后投递
```

**迁移结论**：手动 `available_at` 逻辑**可删**，用 Dramatiq 的 `delay`。注意文档警告："消息 broker 不是数据库，调度消息应只占总量的小部分"。

### 3.5 持久化

**当前实现**：
- `processing_runs` / `processing_spans`：业务账本和阶段流水，PG 持久化
- `task_outbox`：投递意图，PG 持久化
- Redis Stream：消息载体，Redis 持久化（RDB/AOF）

**Dramatiq 对应**：
- 消息存在 Redis（Dramatiq Redis broker 用 LIST + visibility timeout）
- Redis 配 RDB/AOF 持久化，重启不丢
- 但 Dramatiq 的消息是"投递载体"，不是"业务账本"

**迁移结论**：
- `processing_runs` / `processing_spans` **必须保留**，业务账本，Dramatiq 不替代
- `task_outbox` 表**删除**
- Redis 持久化配置不变
- 业务状态真相源仍在 PG 的 `processing_runs`，Dramatiq 消息只是触发执行的信号

### 3.6 Lease（fencing）

**当前实现**（`runtime.py:76-194`）：
- `claim_run`：原子 CAS，pending -> running，写 token + epoch + lease_expires_at
- `complete_run` / `fail_run` / `renew_lease`：校验 token + epoch + lease 未过期
- `_heartbeat_loop`：每 15s 续租，lease=900s

**Dramatiq 对应**：**没有 fencing**，只有 visibility timeout（消息级）。at-least-once 投递，重复执行靠业务幂等。

**迁移结论**：唯一不能完全交给 Dramatiq 的部分。采用方案 A 保留 fencing：
- `claim_run` / `complete_run` / `fail_run` 的 CAS 保留
- `_heartbeat_loop` 保留（任务可能超过 Dramatiq 的 visibility timeout，需要续租防止重投）
- Dramatiq 消息重复投递时，`claim_run` 返回 None 自然吸收
- 代码改动最小，安全性最高

---

## 4. 迁移对照总表

| 保证项 | 当前实现 | Dramatiq 对应 | 结论 |
|---|---|---|---|
| 重试 | `retry_run` + 退避自写 | `max_retries` + `min/max_backoff` + `throws` | **删自建，用 Dramatiq** |
| 死信 | 无独立表，落 Run 终态 | 内置 DLQ | **额外赠送，Run 终态保留** |
| 崩溃重投 | Reaper 扫 Run 补 Outbox | visibility timeout 自动重投 | **删 Outbox 补投，保留简化版扫 lease 过期** |
| 延迟 | `available_at` 手动 | `send_with_options(delay=)` | **删自建，用 Dramatiq** |
| 持久化 | PG 账本 + Redis Stream + Outbox | PG 账本 + Redis LIST | **账本保留，Outbox 删** |
| Lease | token+epoch+lease+心跳 | 无，只有 visibility timeout | **删除 lease，改用 span 心跳判卡死** |

---

## 5. 待保留 vs 待删除清单

### 保留

| 组件 | 文件 | 理由 |
|---|---|---|
| 业务账本 | `models/task_runtime.py` 的 `ProcessingRun` / `ProcessingSpan` | 业务审计必需，Dramatiq 不替代 |
| 错误分类 | `errors.py` 的 `TransientTaskError` / `TerminalTaskError` | Dramatiq 的 `throws` / `retry_when` 使用 |
| Handler 注册 | `tasks.py` 的 `RUN_HANDLERS` / `register_run_handler` | 业务派发机制不变 |
| 简化版状态机 CAS | `runtime.py` 的 `claim_run` / `complete_run` / `fail_run`（简化版，只靠 status）| Run 状态准确性保障，不依赖 token/epoch |
| Span 心跳 | handler 内部各阶段调 `begin_span` / `end_span` | 事件驱动刷新 span updated_at，Reaper 据此判卡死；对齐 WeKnora 的 SpanTracker |
| 简化版 Reaper | 嵌入 worker 进程（`after_process_boot` 启独立线程），5min 扫一次，标 Run failed | 扫"running 且 span 心跳超 5min 没动" + "pending 且 created_at 过旧" |
| 失败回调 Middleware | 自定义 `RunFailureMiddleware`，复用 EventLoopThread 调 async | Dramatiq 重试耗尽 / 终态错误时标 Run failed |
| Executor 主体 | `executor.py` 的 `execute_run_message` | 保留 claim/handler 派发/commit；删退避/心跳/retry_run |

### 删除

| 组件 | 文件 | 理由 |
|---|---|---|
| Outbox 表 | `models/task_runtime.py` 的 `TaskOutbox` | 删 Outbox 策略 |
| Outbox 投递 | `outbox/` 整个目录 | Dramatiq 内置投递 |
| Fencing CAS | `runtime.py` 的 token/epoch 校验逻辑 | handler 已有幂等检查，CAS 是冗余 |
| 心跳续租 | `executor.py` 的 `_heartbeat_loop` | 改用 span 心跳，不再续租 lease |
| lease 字段 | `ProcessingRun.lease_expires_at` | 删 lease，改用 span 心跳判卡死 |
| execution_token / execution_epoch | `ProcessingRun` 的两个字段 | fencing CAS 删除后不再需要 |
| heartbeat_at 字段 | `ProcessingRun.heartbeat_at` | 删续租后不再需要 |
| worker_id 字段 | `ProcessingRun.worker_id` | fencing 删除后不再需要（或保留仅作日志诊断）|
| 退避计算 | `executor.py` 的 `_retry_delay` / `_handle_failure` 的退避和重试调度部分 | Dramatiq Retries middleware 接管；但 `_handle_failure` 里调 `fail_run` 标终态失败的逻辑保留 |
| retry_run | `runtime.py` 的 `retry_run` | Dramatiq 内置重试 |
| Outbox 双写 | `runtime.py` 的 `create_run_with_outbox` | 改为直接 `actor.send()` |
| Taskiq broker | `broker.py` 的 `RedisStreamBroker` 配置 | 换 Dramatiq `RedisBroker` |
| Outbox sender | `tasks.py` 的 `send_task_message` | 不再需要 |
| Outbox publisher 容器 | `docker-compose.yml` 的 `outbox-publisher` 服务 | 不再需要 |
| multimodal 队列 | `broker.py` 的 `MULTIMODAL_QUEUE` | 当前未使用 |
| low 队列 | `broker.py` 的 `LOW_QUEUE` | 删 low，wiki_generate 改到 default |

---

## 6. 当前配置参数（迁移参考）

来源：`app/config/settings.py` + `docker-compose.yml`。

| 参数 | 当前值 | 迁移后对应 |
|---|---|---|
| `TASK_WORKER_CONCURRENCY` | 16 | Dramatiq `--threads 16` |
| `TASK_LEASE_SECONDS` | 900（15min）| **删除**，改用 span 心跳判卡死 |
| `TASK_HEARTBEAT_SECONDS` | 15 | **删除**，改用 span 心跳（事件驱动）|
| `TASK_MAX_AUTO_RETRIES` | 3 | Dramatiq `max_retries=3` |
| `TASK_RETRY_BASE_SECONDS` | 5 | Dramatiq `min_backoff=5000` |
| `TASK_RETRY_MAX_SECONDS` | 300 | Dramatiq `max_backoff=300000` |
| shared worker 并发 | `--max-async-tasks 14` | 合并到单 worker `--threads 16` |
| critical worker 并发 | `--max-async-tasks 2` | 合并到单 worker `--threads 16` |
| Reaper 扫描间隔 | 30s（Outbox 内）| **改为 5min**（嵌入 worker，对齐 WeKnora）|
| Dramatiq 心跳超时 | - | 默认 60s（worker 进程崩溃后 60s 重投未 ack 消息）|
| Dramatiq time_limit | - | 需配置，覆盖最长任务（如 3600000ms=1h）|
| Span 心跳阈值 | - | 5min（running 且最近 span updated_at 超 5min 没动 -> 标 failed）|

---

## 7. 未决问题

以下问题在后续【制定方案】阶段需要进一步确认：

1. ~~**失败回调 Middleware 的 async 适配**~~：已决策--复用 Dramatiq 的 `EventLoopThread`（`get_event_loop_thread().run_coroutine()`）。
2. ~~**docker-compose 服务调整**~~：已决策--删除 `outbox-publisher`，合并为单个 `task-worker`，`dramatiq app --queues critical default --threads 16`。
3. ~~**Run 状态机简化**~~：已决策--删除 token/epoch/lease/heartbeat 字段，保留简化版 CAS（只靠 status）。
4. **handler 幂等策略调整**：当前 handler 的幂等检查是抛 `TerminalTaskError` 拒绝重做，用户重试会被挡。后续重写 handler 时需调整为允许重做已完成的步骤。
5. **commit_success 失败的已知限制**：DB 临时故障导致 `commit_success` 失败时，业务可能已部分写入，但 Run 最终被 Reaper 标 failed。当前接受这个不完美。
6. **Span 心跳的 API 设计**：需要设计 `begin_span(run_id, span_name)` / `end_span(span_id)` 的接口，handler 重写时调用。对齐 WeKnora 的 SpanTracker 但用 Python async 实现。
7. ~~**Dramatiq time_limit 配置**~~：已决策--所有 actor 统一 `time_limit=3600000`（1 小时），span 心跳 + Reaper 是主要卡死检测机制，time_limit 是 Dramatiq 的补充。
8. **Span 心跳阈值与 Reaper 间隔的协调**：Reaper 5min 扫一次，span 心跳阈值 5min。如果 handler 某个阶段执行超过 5min（如 embedding 5K chunks），span 不刷新，Reaper 会误杀。需要 handler 在长阶段内部定期刷新 span（如每 2min 更新一次 span 的 metrics 或 updated_at）。
