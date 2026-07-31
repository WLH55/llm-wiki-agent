# RAG 独立路线

## 0. 状态

- **phase**: Execute
- **approval status**: Runtime decision accepted; implementation in progress
- **status**: IN PROGRESS
- **active project**: llm_wiki3.0
- **active workdir**: `D:\AI\llm-wiki-agent`
- **Goal**: 先走通可独立使用的 RAG 知识库闭环，为后续 Wiki 能力保留公共内容基础。

## 0.1 执行状态（2026-07-31）

运行时方案已由 [ADR-0018](../context/docs/adr/0018-taskiq-outbox-fenced-run-runtime.md) 固化：PostgreSQL 是 Run 和 Outbox 的权威状态，Taskiq + Redis Streams 仅负责至少一次传输，Worker 通过 lease、fencing token 与 epoch 防止过期执行提交结果。

### 已完成

- 数据库迁移 `003_task_runtime` 和 `004_rag_revisions`：Run/Span/Outbox、不可变 `DocumentRevision`、候选 chunk 与 Active Revision 指针已落库。
- 上传链路在一次事务中创建 `Document`、`DocumentRevision`、`document_process` Run 和待投递 Outbox；不再直接调用 RQ 入队。
- `document_process` Handler 按 Revision 从对象存储读取文件并解析，写入未 embedding 的候选 chunks；同一 fenced 事务中创建 critical `rag_index` 子 Run 和 Outbox。
- `rag_index` Handler 在全部 embedding 成功后原子写入向量并激活 Revision；embedding 失败保留旧 Active Revision。
- 向量和 BM25 检索均限定为 `documents.active_revision_id`，状态 API 从最新 Revision/Run 推导状态。
- Compose 已部署 Outbox Publisher、Taskiq shared Worker 和 Taskiq critical Worker；旧 RQ 模块、依赖、测试和容器已删除。
- Taskiq broker、Outbox 发布/重试/Reaper 与 Run 领取、续租、fencing 已有 PostgreSQL 集成测试覆盖；本地 Docker 已验证上传经 Outbox、Taskiq 到 Revision 激活的闭环。

### 未完成，不能视为闭环

- 完成 Redis Streams 崩溃恢复、重复投递和旧 Worker 租约失效后的端到端验证。

### 当前验收标准

1. 上传成功后，数据库中必须同时存在 Document、Revision、`document_process` Run 和未发布 Outbox；不得依赖直接 RQ 入队。
2. 文档解析成功后，候选 chunks 与 `rag_index` Run/Outbox 必须原子存在，且旧 `active_revision_id` 不变。
3. embedding 失败时，旧 Active Revision 仍可搜索；成功时才原子激活新 Revision。
4. 任意重复消息或 lease 失效的旧 Worker 都不能写入重复 chunks、错误终态或过期激活结果。
5. 在部署的 Publisher 和 Taskiq Worker 运行时，未发布 Outbox 能被投递、失败发布能重试、Worker 崩溃前未确认的消息能被恢复处理。

## 0.2 当前边界

### In Scope

- 知识库创建与 RAG 配置。
- 文档上传、解析、分块和 embedding。
- 候选 Document Revision 与 Active Revision 两阶段激活。
- 向量检索、关键词检索和 RRF 融合。
- 处理任务状态、失败、重试、心跳和基础进度查询。
- RAG 路线的 API、前端最小操作闭环和自动化测试。

### Out of Scope

- Wiki 页面自动生成、Wiki 搜索和图谱生成。
- Wiki 页面写入 RAG 检索池。
- RAG 与 Wiki 的联合召回或联合排序。
- 多模型路由和复杂 Agent 工作流。

## 1. Context Sources

- `mydocs/context/CONTEXT.md`
- `mydocs/context/docs/adr/0010-mvp-wiki-rag-separation.md`
- `mydocs/context/docs/adr/0012-approved-rag-wiki-database-boundaries.md`
- `mydocs/context/docs/adr/0013-shared-content-chunk-substrate.md`
- `mydocs/context/docs/adr/0014-processing-run-retry-boundary.md`
- `mydocs/context/docs/adr/0015-processing-span-concurrency-model.md`
- `mydocs/context/docs/adr/0016-two-phase-active-revision.md`
- `mydocs/context/docs/adr/0017-redis-ephemeral-wiki-coordination.md`
- `mydocs/context/docs/adr/0018-taskiq-outbox-fenced-run-runtime.md`
- `mydocs/specs/2026-07-27_数据库表逐表审批记录.md`
- `mydocs/context/2026-07-29_WeKnora处理任务与恢复机制调研.md`

## 1.1 Codemap Used

- **project**: 当前已有 `mydocs/codemap/2026-07-24_15-30_backend项目总图.md`。
- **feature slices**:
  - `backend/app/workers/parse_document.py`
  - `backend/app/workers/queue.py`
  - `backend/app/search/service/search.py`
  - `backend/app/models/document.py`
  - `backend/app/models/chunk.py`
  - `backend/alembic/versions/001_initial.py`

## 1.2 Research Findings

1. 当前运行时仍使用旧的 `documents.status` 和 `content_chunks.doc_id` 模型。
2. 已批准的数据设计要求引入 `document_revisions`、`processing_runs`、`processing_spans`，并以候选 Revision 完成索引后再激活。
3. 当前文档 Worker 在一次任务中直接解析、embedding、写入 chunks，并立即将文档标记为 `processed`，与两阶段激活设计不一致。
4. 当前 RAG 检索已具备向量、关键词和 RRF 编排，但没有按 `documents.active_revision_id` 过滤共享 chunks。
5. 当前 Wiki 路线明确与 RAG 分离，因此本轮可以只验证 RAG 的处理和检索闭环。
6. `backend` 与 `worker` 当前复用同一镜像和 `app` 包，但由不同入口进程执行；Parser 实现虽然位于 `backend/app/parsers`，正式摄取时由 Worker 导入和执行，不在上传请求内逐页解析。
7. 当前 RQ Worker 一次只消费一个 Job；`asyncio.run(parse_document_task(...))` 允许单 Job 使用协程，但不会让同一 Worker 并发消费多个 Job。
8. WeKnora 使用 Go Asynq 的进程内并发池，单实例默认 32 个任务槽位，并通过加权队列和 Job 内 `errgroup.SetLimit` 控制两层并发；该数值不能直接复制到 Python 的本地 Parser 流水线。
9. 本项目的 I/O 阶段适合协程并发，本地 PDF/DOCX/OCR 等阻塞阶段需要独立的受限线程池、进程池或资源队列。是否保留 RQ 尚未批准，`arq` 仅作为 async-native 候选进入评估。

## 1.3 Open Questions

- RAG 独立路线的第一验收边界，是只要求后端 API 闭环，还是同时要求前端上传、任务状态和检索页面可操作？
- 是否保留当前 RAG 检索实现中的 PostgreSQL `tsvector` 路线，还是本轮同步切换到已记录的 BM25 方案？
- 文档处理完成后，首版是否必须支持取消和业务重跑，还是先完成自动重试与失败恢复？
- Worker 运行时是否必须支持单进程内同时执行多个独立 Job 协程？
- 保留 RQ 并用多个 Worker 进程扩容，还是切换到 async-native Redis 队列？若切换，框架选择需单独比较并批准。
- 首版允许多少个并发 Processing Run？Parser、Embedding/LLM 和数据库写入是否采用不同的并发预算？
- 多队列只需要优先级和公平调度，还是必须为长耗时任务提供独立容量，避免共享槽位被占满？

## 1.4 Next Actions

1. 先批准 Worker 的负载假设和并发目标，包括期望排队时间、单机资源与外部模型限流。
2. 对 RQ 多进程方案与 async-native 方案进行同一套能力矩阵评估：并发、重试、固定 Job ID、取消、超时、延迟任务、崩溃恢复、优雅停机、监控和测试支持。
3. 批准运行时后，再审批队列划分、各资源并发预算和部署拓扑。
4. 通过逐项讨论确定 RAG 路线的完整验收边界。
5. 对数据库迁移、模型、Worker、检索服务和 API 建立可执行 Plan。
6. 等待明确的 `Plan Approved` 后再进入 Execute。

## 2. Innovate

- **Skipped in current Research step**：先确认范围和领域边界；若发现多种处理链方案存在不可逆取舍，再进入 Innovate。

## 3. Plan

待 Research 和领域模型确认后填写。
