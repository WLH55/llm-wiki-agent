# Taskiq + Transactional Outbox 可靠任务机制解读

> 对应提交：`4a707a5 feat:任务队列模块设计`
> 涉及目录：`backend/app/workers/`、`backend/app/models/task_runtime.py`

本文档解释本项目任务队列的设计：为什么用 Outbox、三张表如何配合、字段含义、完整投递与执行流程，以及如何新增一种任务。

---

## 一、为什么需要 Outbox 表

最朴素的做法是业务代码里直接调 taskiq 发消息：

```python
# 不可靠的做法
async def upload_document():
    db.add(ProcessingRun(status="pending"))        # 1. 写数据库
    await db.commit()
    await process_run_shared.kicker().kiq(run_id)  # 2. 发 Redis 消息
```

两个致命问题：

1. **先发消息后提交**：消息发出去了，事务却回滚 → worker 收到消息但查不到 run。
2. **先提交后发消息**：事务提交了，发消息时 Redis 挂了/网络抖动 → run 永远卡在 pending，没人处理。

根本原因：**数据库事务和发消息是两个独立系统，无法做成一个原子操作。**

**Transactional Outbox（事务性发件箱）模式**的解法：

> 不在业务流程里直接发消息，而是在同一个数据库事务里，把"要发的消息"写进一张专门的表（outbox）。事务提交成功 = 业务数据和"发消息意图"同时落库。然后由一个独立的后台循环，把 outbox 里的记录可靠地搬运到 Redis。

即使搬运过程崩溃，重启后还能从 outbox 表继续，消息不会丢。

---

## 二、三张表的职责分工

```
┌─────────────────────────┐
│   processing_runs       │  任务账本（唯一真相源）
│   - 状态机 pending→      │  记录"这个任务是什么、进行到哪了、谁在执行"
│     running→succeeded   │
│   - 租约 token/epoch    │
└───────────┬─────────────┘
            │ 1:N
            ▼
┌─────────────────────────┐         ┌─────────────────────────┐
│   processing_spans      │         │      task_outbox        │
│   执行尝试/阶段记录       │         │   待投递消息（发件箱）    │
│   - 每次 worker 尝试一条  │         │   - "我要发一条消息"      │
│   - token 消耗/错误诊断  │         │   - 搬运成功后标记         │
│   - 重试不覆盖历史        │         │   - 支持延迟/重试/锁定     │
└─────────────────────────┘         └─────────────────────────┘
```

| 表 | 角色 | 生命周期 |
|---|---|---|
| `processing_runs` | **账本**：任务是什么、当前状态、谁持有执行权 | 任务创建到终态，1 条 |
| `processing_spans` | **流水**：每次执行尝试的可观测记录 | 每次尝试 1 条，自动重试会新增 |
| `task_outbox` | **发件箱**：等待搬到 Redis 的消息 | 投递成功后保留（已发布状态），重试产生新行 |

关键点：**outbox 不保存业务数据，只保存"要发什么消息"的最小信息。** 真正的任务参数全在 `processing_runs.options_snapshot` 里，消息正文只有一个 `run_id`。

---

## 三、task_outbox 表字段逐一解释

来自 `backend/app/models/task_runtime.py`：

```python
class TaskOutbox(Base):
    __tablename__ = "task_outbox"
```

| 字段 | 类型 | 含义 |
|---|---|---|
| `id` | int PK | 自增主键 |
| `run_id` | int | **关联 `processing_runs.id`**。这条消息要投递哪个任务 |
| `task_name` | str(100) | taskiq 任务名。目前固定 `"process_run"`，预留扩展 |
| `queue_name` | str(50) | 目标 Redis Stream 名：`llmwiki:tasks:critical/default/multimodal/low` |
| `available_at` | datetime | **最早可投递时间**。≤ now 才会被 publisher 领取。用于延迟重试 |
| `publish_attempts` | int | 已尝试投递次数（用于指数退避计算） |
| `lock_token` | UUID \| None | **领取凭证**。publisher 领取时写入，确认时校验，防并发误确认 |
| `locked_until` | datetime \| None | 领取锁的过期时间。过期后其他 publisher 可重新领取 |
| `published_at` | datetime \| None | **投递成功时间**。`NULL` = 还没发出去；非空 = 已成功 XADD 到 Redis |
| `last_error` | Text \| None | 最近一次投递失败的错误信息（截断 2000 字符） |
| `created_at` | datetime | 行创建时间（DB 默认 now()） |
| `updated_at` | datetime | 行最后更新时间（DB 默认 now()） |

### 三个典型状态

**状态 A：刚创建，待投递**

```
published_at = NULL
lock_token = NULL
locked_until = NULL
available_at = 创建时间
publish_attempts = 0
```

publisher 轮询时会捞到它。

**状态 B：被某个 publisher 领取了，正在投递**

```
published_at = NULL
lock_token = a3f9...（UUID）
locked_until = now + 30s
available_at = 原时间
publish_attempts = 0
```

其他 publisher 看到 `locked_until` 未过期，不会重复领取。如果这个 publisher 崩溃了，30 秒后锁过期，别的 publisher 能重新领。

**状态 C：投递成功（终态）**

```
published_at = now（非空）
lock_token = NULL
locked_until = NULL
last_error = NULL
publish_attempts = 1
```

publisher 不再处理它。记录保留用于审计。

---

## 四、Outbox 机制完整流程

### 步骤 1：业务创建 Run + Outbox（同一事务）

`runtime.py` 的 `create_run_with_outbox`：

```python
async def create_run_with_outbox(db, *, ..., queue_name, available_at=None):
    run = ProcessingRun(status="pending", ...)
    db.add(run)
    await db.flush()                      # 拿到 run.id
    db.add(TaskOutbox(
        run_id=run.id,
        task_name="process_run",
        queue_name=queue_name,
        available_at=available_at or now(),
    ))
    return run
    # 调用方 await db.commit() —— Run 和 Outbox 在同一个事务里落库
```

**这是整个可靠性的基石**：`processing_runs` 行和 `task_outbox` 行在同一事务里，要么都成功要么都失败，不存在"有 run 没 outbox"或"有 outbox 没 run"。

### 步骤 2：Publisher 轮询领取

`outbox.py` 的 `claim_outbox_batch`：

```python
select(TaskOutbox)
.where(
    TaskOutbox.published_at.is_(None),          # 还没投递
    TaskOutbox.available_at <= claim_time,       # 到了可投递时间
    or_(
        TaskOutbox.lock_token.is_(None),         # 没被领取，或
        TaskOutbox.locked_until < claim_time,    # 领取锁已过期
    ),
)
.order_by(available_at, id)
.limit(batch_size)
.with_for_update(skip_locked=True)              # 关键
```

两个并发安全机制：

- **`SKIP LOCKED`**：多个 publisher 实例同时查询时，被其他事务锁住的行会被直接跳过，不会阻塞、不会重复领取。
- **`lock_token` + `locked_until`**：领取时生成一个随机 UUID 写入，并设 30 秒过期。后续确认/释放必须带上这个 token，且锁未过期才能操作——这叫 **fencing token**，防止"领取后卡住、锁过期被别人重领、然后自己又来确认"的竞态。

领取后给每一行写入新的 `lock_token` 和 `locked_until`。

### 步骤 3：发送到 Redis 并确认

`publisher.py` 的 `publish_outbox_claim`：

```python
try:
    await sender(claim.task_name, claim.run_id, claim.queue_name)  # 调 taskiq kick
except Exception as exc:
    # 失败：释放锁，设置重试时间
    await release_outbox_claim(db, claim, error=str(exc),
                               retry_at=now + 5s)
    return False
# 成功：标记已发布
return await mark_outbox_published(db, claim)
```

注意**领取和发布是分开的两个事务**（`outbox_service.py` 先领一批并提交，然后逐条开新事务发布）。这样设计是为了：发 Redis 是网络 IO，可能慢，不长占数据库行锁。

### 步骤 4：成功标记 vs 失败释放

**成功**（`outbox.py` 的 `mark_outbox_published`）：

```python
update(TaskOutbox)
.where(
    TaskOutbox.id == claim.outbox_id,
    TaskOutbox.published_at.is_(None),
    TaskOutbox.lock_token == claim.lock_token,    # 必须是领取者本人
    TaskOutbox.locked_until > now,                # 锁没过期
)
.values(published_at=now, publish_attempts += 1,
        lock_token=None, locked_until=None, last_error=None)
```

WHERE 条件里同时校验 token 和未过期——如果锁已过期被别人重领了，这次确认影响 0 行（返回 False），不会把别人的投递误标记为成功。

**失败**（`outbox.py` 的 `release_outbox_claim`）：

```python
.values(
    available_at=retry_at,                # 退避后才可再领
    publish_attempts += 1,
    lock_token=None, locked_until=None,    # 释放锁
    last_error=error[:2000],
)
```

不删行，只释放并延后，让下一轮重试。

### 步骤 5：Publisher 常驻循环

`outbox_service.py` 的 `run_outbox_service`：

```
while not stop:
    1. publish_outbox_batch()     # 领一批(100)，逐条发布
    2. 每到 reaper 间隔 → run_reaper_batch()
    3. 没消息时 wait 0.5 秒（poll_seconds）
    4. 异常被 catch，记录日志后继续循环，不退出
```

退避算法：

```python
raw_delay = min(retry_max_seconds,
                retry_base_seconds * (2 ** claim.publish_attempts))
# 5s → 10s → 20s → 40s ... 封顶 300s
retry_delay = raw_delay + jitter  # 加 0~20% 随机抖动，防惊群
```

---

## 五、和 processing_runs / processing_spans 的配合时序

一次完整任务的生命周期：

```
① 业务请求
   │
   ├─[同一事务]─→ processing_runs  INSERT (status=pending)
   │             task_outbox       INSERT (published_at=NULL)
   │             db.commit()
   │
② Outbox Publisher 轮询
   │
   ├─→ claim_outbox_batch: 锁 outbox 行
   ├─→ send_task_message → taskiq XADD 到 Redis Stream
   ├─→ mark_outbox_published: outbox.published_at = now
   │
③ Taskiq Worker 收到消息 (只含 run_id)
   │
   ├─[事务]─→ SELECT processing_run
   │         claim_run: UPDATE ... SET status=running, token=xxx, epoch=1
   │         processing_spans INSERT (span_name=worker_attempt, status=running)
   │         db.commit()
   │
   ├─→ 启动心跳协程（每15秒 renew_lease 续租）
   ├─→ 执行业务 handler（document_process / rag_index）
   │
   ├─ 成功? → handler 调 context.commit_success(writer)
   │           [事务] writer 写业务结果 + complete_run(run→succeeded)
   │                  finish_worker_attempt(span→succeeded)
   │
   ├─ 瞬时失败? → retry_run():
   │           [事务] run 重置为 pending，清空租约
   │                  task_outbox INSERT 新行(available_at=退避时间)  ← 再次入箱！
   │                  finish_worker_attempt(span→failed)
   │           → 回到步骤 ②，重新走一遍投递
   │
   └─ 终态失败? → fail_run(): run→failed，不再产生 outbox
```

### 重试时为什么新建 outbox 行而不是复用旧行

`runtime.py` 的 `retry_run`：

```python
db.add(TaskOutbox(
    run_id=lease.run_id,
    task_name="process_run",
    queue_name=queue_name,
    available_at=available_at,         # 未来时间（延迟）
    last_error=error_code[:1000],
))
```

旧 outbox 行已经 `published_at` 非空了（它确实成功投递过，只是业务执行失败）。投递本身没失败，所以不该把它退回未发布状态——**投递成功和业务成功是两回事**。业务失败要重投，就新建一条 outbox 记录，这样历史投递记录和重试记录各自独立可审计。

`processing_spans` 同理：每次重试新增一条 span（按 count 计算 attempt 编号），不覆盖上一次的错误信息。这就是为什么三张表设计成"账本 + 流水 + 发件箱"，而不是一张大宽表。

### Reaper 兜底也产生 outbox

`reaper.py` 的 `recover_stalled_runs`：

```python
for run in result.scalars():
    db.add(TaskOutbox(
        run_id=run.id,
        task_name="process_run",
        queue_name=queue_name_for_run(run.run_type),
        available_at=recovery_time,
        last_error="reaper_recovery",
    ))
```

当 run 卡在 pending 太久、或 running 租约过期，且当前没有未发布的 outbox（说明之前的消息丢了），reaper **补建一条 outbox**，让它重新进入步骤 ② 的投递流程。这是兜"Redis 消息丢了 / consumer 组跳过了消息"的最后一道防线。

注意 reaper 的查询条件 `~unpublished_exists`：**如果已经有一条未发布的 outbox 在路上了，就不重复补**，避免重复消息（虽然重复也不怕，有 claim_run 去重）。

---

## 六、Worker 端执行与租约（防重复执行）

Worker 收到消息后执行 `executor.py` 的 `execute_run_message`：

1. 开事务：读 Run → `claim_run` 原子领取 → `start_worker_attempt` 建 span → 快照 RunIdentity。
2. 关事务（业务执行期间不长占事务）。
3. 启动心跳协程（每 15 秒 `renew_lease`）。
4. 查 handler 表 → `await handler(context)`。
5. 业务 handler **必须**调用 `context.commit_success(writer)`，否则视为契约违规（TerminalTaskError）。
6. 异常分类：
   - `TerminalTaskError` → 不重试，直接 `fail_run`。
   - 其他异常 → 包成 `TransientTaskError`，指数退避后 `retry_run`。
   - `LeaseLostError` → 租约被抢，冒泡（当前 worker 已无权写状态）。
7. `commit_success` 里：先跑业务 writer，再 `complete_run`，同一事务，任一失败整笔回滚。

`claim_run` 是防重复执行的关键（原子 CAS）：

```python
update(ProcessingRun)
.where(
    ProcessingRun.id == run_id,
    or_(status == "pending",
        and_(status == "running", lease_expires_at < now))
)
.values(status="running", execution_token=新token, execution_epoch=epoch+1, ...)
```

两个 worker 同时收到同一条消息（at-least-once 重复投递）时，数据库行锁保证只有一个 UPDATE 命中；第二个 WHERE 不匹配，返回 None，直接 IGNORED。

---

## 七、相关配置项

`backend/app/config/settings.py`：

```python
# ========== Taskiq Worker ==========
TASK_WORKER_CONCURRENCY: int = 16          # broker 一次拉取消息数 / worker 并发度
TASK_CRITICAL_RESERVED_CONCURRENCY: int = 2
TASK_PARSER_PROCESSES: int = 2
TASK_LEASE_SECONDS: int = 900              # Run 执行租约 15 分钟
TASK_HEARTBEAT_SECONDS: int = 15           # 心跳续租间隔
TASK_STREAM_IDLE_TIMEOUT_MS: int = 1_800_000   # Redis XAUTOCLAIM 判定 30 分钟
TASK_OUTBOX_BATCH_SIZE: int = 100          # publisher 每轮领取多少条
TASK_OUTBOX_LOCK_SECONDS: int = 30         # outbox 领取锁 30 秒过期
TASK_OUTBOX_POLL_SECONDS: float = 0.5      # 无消息时轮询间隔
TASK_MAX_AUTO_RETRIES: int = 3             # 业务瞬时失败最多自动重试 3 次
TASK_RETRY_BASE_SECONDS: int = 5           # 退避基数 5 秒
TASK_RETRY_MAX_SECONDS: int = 300          # 退避封顶 300 秒
```

注意区分两组重试：

| 重试 | 触发 | 计数 | 退避 |
|---|---|---|---|
| **Outbox 投递重试** | 调 taskiq `kick()` 抛异常（Redis 连不上） | `task_outbox.publish_attempts` | `outbox_service.py` 指数退避 |
| **业务执行重试** | worker 执行 handler 抛瞬时异常 | `processing_spans` attempt 编号 | `executor.py` 指数退避，新建 outbox |

两者都封顶在 `TASK_RETRY_MAX_SECONDS=300`，但计数和记录完全独立。

---

## 八、如何新增一种任务类型

1. **建表迁移**：三张表已经有了，不用改。
2. **写业务 handler**：

   ```python
   async def my_handler(context: RunExecutionContext) -> None:
       # context.identity.run_id / options_snapshot 读参数
       # ... 执行业务 ...
       async def write_result(db, ctx):
           db.add(MyResult(...))
       await context.commit_success(write_result)   # 必须调
   ```

3. **注册 handler**：在 `tasks.py` 的 `RUN_HANDLERS` 加一行，或启动时调 `register_run_handlers()`。
4. **决定队列**：在 `executor.py` 的 `queue_name_for_run` 加映射（critical/default/low）。
5. **触发任务**：在 API 里调 `create_run_with_outbox(db, run_type="my_type", queue_name=..., ...)`，事务提交即可。不用手动发消息，publisher 会自动搬运。

---

## 九、一句话总结

> `task_outbox` 是"要发的消息"在数据库里的临时落脚点，它和 `processing_runs` 同事务创建，由后台 publisher 可靠地搬到 Redis，搬成功就打标记、搬失败就退避重试；业务失败和 reaper 兜底都通过"新建一条 outbox 行"来触发重新投递。`processing_spans` 则在每次执行时追加一条流水，记录每次尝试的成败和诊断信息。Redis 层只保证消息"至少投递一次"，去重与并发互斥全部下沉到数据库的原子 CLAIM 上。
