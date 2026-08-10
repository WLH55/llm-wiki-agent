# Taskiq、Transactional Outbox 与 Fenced Run Runtime

> 状态：Accepted（2026-07-31）  
> 取代范围：ADR-0014 和 ADR-0017 中关于 RQ 作为业务任务传输层的表述；两份 ADR 对 Run 重试边界和 Redis 临时协调边界的其余结论继续有效。

## 决策

文档解析、索引和后续 RAG/Wiki 处理以 PostgreSQL 中的 `processing_runs` 为权威业务状态，以 Taskiq + Redis Streams 为可恢复的传输层。创建 Run 时必须在同一 PostgreSQL 事务内创建 `task_outbox` 记录；独立 Publisher 领取 Outbox 后才向 Redis Streams 发布任务。

Worker 收到消息只把它视为“尝试处理此 Run”的通知。它必须先以原子条件领取 Run，写入新的 `execution_token`、单调递增的 `execution_epoch` 和有限期 lease。续租、成功、失败、重试及处理结果提交均以 token、epoch 和未过期 lease 为条件。失去 lease 的 Worker 必须放弃内存结果，不能提交过期执行的副作用。

队列按资源和优先级分为 `critical`、`default`、`multimodal`、`low`。`rag_index` 使用 `critical`；文档解析使用 `default`。共享 Worker 消费普通队列，critical Worker 专门预留给高优先级索引。消息只携带 Run 标识，真实输入从 PostgreSQL 和对象存储按 Run scope 重新读取。

## 原因

直接“写数据库后调用 RQ”存在双写缺口：数据库提交成功而发布失败时，Run 会永久停在 `pending`。Outbox 把 Run 和待发布事件置于同一数据库事务内，Publisher 可以重试发布并由 Reaper 为遗失投递补建 Outbox。

Redis Streams、网络和 Worker 进程都可能产生重复投递或延迟恢复，因此传输层只能提供至少一次交付。lease 加 fencing token 让 PostgreSQL 拒绝旧 Worker 的终态更新，从而避免一个过期执行覆盖已接管执行的结果。

## 运行语义

- Publisher 使用 `FOR UPDATE SKIP LOCKED` 领取 Outbox；仅在 Taskiq 发布成功后设置 `published_at`。发布失败会释放锁并按退避时间重试。
- Run 的业务重试复用同一 Run，回到 `pending` 并创建新的延迟 Outbox；终态 Run 的业务重跑才创建新 Run，并通过 `retry_of_run_id` 建立追溯关系。
- Handler 的不可重复副作用必须与 `complete_run()` 放入同一 fenced PostgreSQL 事务。重复消息、过期 Worker 或 Publisher 重发都不得产生重复候选 chunks、重复激活或错误覆盖。
- Taskiq 当前配置使用 `ack-type=when_executed`。业务异常在 Handler 内被分类并持久化后正常返回；进程在确认前崩溃时，Redis Stream pending 消息仍可被恢复消费。

## 后果与约束

- RQ 队列、Worker 与旧的整链路解析任务已删除；上传、解析和索引只能经 Outbox 与 Taskiq Run Runtime 进入执行。
- Outbox 提供至少一次投递，不提供端到端恰好一次；幂等和 fencing 是 Handler 的必需约束。
- Worker 部署必须包含 Outbox Publisher、shared Taskiq Worker 和 critical Taskiq Worker；仅运行旧 RQ Worker 会导致 Outbox 永远不被投递。
- Redis 不保存权威业务进度、解析结果或激活事实；这些事实必须在 PostgreSQL 中提交。
- 本 ADR 不决定 Parser 进程池容量、embedding 限流或 Wiki 生成编排，它们需要分别以运行指标和专项 ADR 决定。

## 实施状态

已实现并有 PostgreSQL 集成测试：Run/Span/Outbox 模型与迁移、Outbox Publisher/Reaper、Taskiq broker、租约与 fencing、Revision 化上传、`document_process` Handler、`rag_index` Handler、Active Revision 检索过滤，以及从 Revision/Run 推导的文档状态 API。Compose 已部署 Publisher、shared Worker 和 critical Worker；本地 Docker 已验证上传经 Outbox、Taskiq 到 Revision 激活的闭环。

尚未完成：Redis Streams 崩溃恢复、重复投递和旧 Worker 租约失效后的端到端验证。这些缺口不改变本决策，但仍是生产级高可用验收的一部分。
