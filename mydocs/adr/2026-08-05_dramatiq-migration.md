# ADR: 任务队列从 Taskiq + Outbox 迁移到 Dramatiq

> **Status**: Accepted
> **Date**: 2026-08-05
> **Decision Maker**: 用户（经 21 题 grilling 确认）
> **Supersedes**: Taskiq + Redis Stream + Transactional Outbox 三表运行时

---

## 背景

当前项目使用 Taskiq（薄框架）+ Redis Stream（裸 broker）+ 自建 Transactional Outbox 实现任务队列。自建了 Outbox Publisher、Reaper、fencing（token+epoch+lease+心跳续租）一整套投递设施。经 WeKnora 对比分析（`task-queue-comparison-weknora-vs-llm-wiki-agent.md`），发现自建投递复杂度高，而 WeKnora 靠 asynq 成熟框架兜底，验证了"直接入队 + 恢复扫描"的可行性。

## 决策

将任务队列迁移到 **Dramatiq + Redis**，删除 Outbox 和 fencing，借鉴 WeKnora 的 span 心跳判卡死机制。

### 核心决策链

1. **删除 Outbox**：先提交 DB 再入队，入队失败标 failed，崩溃窗口靠 Reaper 兜底（对齐 WeKnora）
2. **换 Dramatiq**：内置重试/死信/延迟/崩溃重投，砍掉自建件
3. **删除 fencing**：handler 已有幂等检查，CAS 是冗余；改用 span 心跳判卡死
4. **多队列路由**：同函数多 actor 注册（Dramatiq queue_name 固定死，源码验证）
5. **队列简化**：删 multimodal/low，只保留 critical + default
6. **Worker 拓扑**：单容器 `dramatiq --queues critical default --threads 16`
7. **失败回调**：自定义 Middleware，复用 Dramatiq EventLoopThread 调 async
8. **Reaper**：嵌入 worker 进程，5min 扫 span 心跳 + pending 过旧，标 Run failed
9. **Span 心跳**：handler 各阶段调 `begin_span`/`end_span`，事件驱动刷新（对齐 WeKnora SpanTracker）

## 理由

- **不想过度设计**：WeKnora 验证"成熟框架兜底 + 恢复扫描"够用
- **砍自建复杂度**：Outbox/Publisher/Reaper/fencing/退避计算全删，交给 Dramatiq
- **并发能力不损失**：全部任务是 IO 密集，Dramatiq AsyncIO middleware 和 Taskiq 并发等价（源码验证）
- **FastAPI 适配无摩擦**：进程分离，入队侧 `actor.send()` 更简单

## 后果

### 正面
- 删除 `outbox/` 整个目录 + Outbox publisher 容器
- 删除 fencing CAS + 心跳续租 + 退避计算 + retry_run
- 投递可靠性交给 Dramatiq 内置机制
- 队列拓扑简化（4 条 -> 2 条）

### 负面
- 双写窗口：DB 提交后入队前崩溃可能丢任务，靠 Reaper 兜底
- commit_success 失败的已知限制：业务可能部分写入但 Run 标 failed
- handler 幂等策略需后续调整（当前拒绝重做，需改为允许重做已完成步骤）
- Span 心跳阈值与长阶段需协调（长阶段内部定期刷新 span）

## Trace to Sources

- `mydocs/dramatiq-migration-decision.md`（grilling 21 题决策记录）
- `mydocs/specs/2026-08-05_00-00_Dramatiq任务队列迁移.md`（SDD Spec）
- Dramatiq 源码：`actor.py` / `asyncio.py` / `retries.py` / `brokers/redis.py` / `middleware/middleware.py`
- WeKnora 源码：`knowledge_housekeeping.go` / `knowledge_span_tracker.go`
