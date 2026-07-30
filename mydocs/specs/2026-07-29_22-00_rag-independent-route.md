# RAG 独立路线

## 0. 状态

- **phase**: Research
- **approval status**: Research Active
- **status**: LOCKED
- **active project**: llm_wiki3.0
- **active workdir**: `D:\AI\知识库设计\llm_wiki3.0`
- **Goal**: 先走通可独立使用的 RAG 知识库闭环，为后续 Wiki 能力保留公共内容基础。

## 0.1 当前边界

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

## 1.3 Open Questions

- RAG 独立路线的第一验收边界，是只要求后端 API 闭环，还是同时要求前端上传、任务状态和检索页面可操作？
- 是否保留当前 RAG 检索实现中的 PostgreSQL `tsvector` 路线，还是本轮同步切换到已记录的 BM25 方案？
- 文档处理完成后，首版是否必须支持取消和业务重跑，还是先完成自动重试与失败恢复？

## 1.4 Next Actions

1. 通过逐项讨论确定 RAG 路线的验收边界。
2. 对数据库迁移、模型、Worker、检索服务和 API 建立可执行 Plan。
3. 等待明确的 `Plan Approved` 后再进入 Execute。

## 2. Innovate

- **Skipped in current Research step**：先确认范围和领域边界；若发现多种处理链方案存在不可逆取舍，再进入 Innovate。

## 3. Plan

待 Research 和领域模型确认后填写。
