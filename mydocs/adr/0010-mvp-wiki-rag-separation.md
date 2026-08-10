# MVP Wiki/RAG 独立运行

> 状态：Accepted（2026-07-27）<br>
> 取代：[ADR-0009](0009-retrieval-architecture.md) 中“Wiki 页面在 MVP 写入 `content_chunks` 并固定加权 1.3”的决策。<br>
> 修订：2026-07-28 按 [ADR-0012](0012-approved-rag-wiki-database-boundaries.md) 同步最终表边界；摄取底座按 [ADR-0013](0013-shared-content-chunk-substrate.md) 改为共享 Active Chunk Set；Redis 短期协调按 [ADR-0017](0017-redis-ephemeral-wiki-coordination.md) 执行。

## Context

参考项目的源码并没有实现 Wiki 页面写入 RAG chunk 的链路：`ChunkTypeWikiPage`、删除逻辑和 WikiBoost 插件存在，但缺少任何对应的 upsert/写入端。因此，源码能证明“曾有融合意图且实现未闭环”，不能证明当前的双路径分离是经过明确取舍后的最终设计。

同时，Wiki 页面基于具体 Document Revision 的完整解析内容生成。若原文 chunk 与派生 Wiki 内容直接进入同一召回池，同一事实可能以两种表述重复占用 top-k；固定的 Wiki boost 还可能让二手转述压过一手原文，增加幻觉和溯源风险。这个风险针对“派生 Wiki 页面进入 RAG 召回池”，不妨碍 Wiki 生成复用原始文档的持久化共享 chunks。

## Decision

MVP 同时完成两条能力闭环。摄取层共享，派生数据与召回面保持独立：

- `knowledge_search` 只检索 Active Document Revision 派生的 `content_chunks`；该表不保存 `chunk_type` 或任何 Wiki 页面字段。
- `wiki_search` 只检索 `wiki_pages`，不触发 Wiki 页面切块、embedding 或 `content_chunks` 写入。
- 不启用 WikiBoost，不在 RAG 结果中对 `wiki_page` 做 1.3 倍或其他固定加权。
- `kb_rag_configs.vector_enabled` / `keyword_enabled` 控制 RAG 路径，`kb_wiki_configs.enabled` 控制 Wiki 生成与独立检索；同时开启表示“两条能力都可用”，不表示结果已融合。
- MVP 不做跨路径联合排序、自动混合 top-k 或 query 级手动模式开关；调用方显式选择 `knowledge_search` 或 `wiki_search`。

## Schema 边界

`content_chunks` 只保存当前 Active Revision 派生的共享原文块，同时供 RAG 召回与 Wiki Map 消费；它不保存 `chunk_type`、`wiki_page_id` 或其他 Wiki 页面内容字段。Wiki 血缘由独立的 `wiki_page_document_refs` 与 `wiki_page_evidence_refs` 表表达；证据以具体 Revision、准确引文和原文位置长期成立，并可通过可空的 `content_chunk_id` 回到生成时使用的共享 chunk。

Wiki 按 `chunk_index` 完整遍历 Active Chunk Set，并将相邻 chunks 确定性组合成 token 预算内的 Map 批次，再执行“批次级 Map -> 文档级 Reduce -> 跨文档按 slug Reduce”；不得重建一个超长字符串后截断。MVP 不保存跨运行 checkpoint：manifest 与 Map 结果只存在于当前 Worker 内存，失败或进程退出后从同一 Active Chunk Set 完整重做。`processing_runs` 与 `processing_spans` 保存权威状态和进度；Redis 只承担 RQ 队列以及 [ADR-0017](0017-redis-ephemeral-wiki-coordination.md) 批准的可丢失短期协调。全部批次未成功时不得部分更新 Wiki；缺块或顺序不一致时任务显式失败，Wiki Worker 不得绕过共享底座秘密重解析原文件。具体契约以逐表审批 Spec 为准。

## 融合启用门槛

完成 Wiki 与 RAG 两条独立路径后，只有满足以下条件才另立 ADR 讨论融合：

1. 使用同一批真实查询分别评估 RAG-only、Wiki-only，建立 Recall@K、nDCG/MRR、引用正确率和答案忠实度基线。
2. 明确融合目标是提升答案质量，而不是仅提高 Wiki 内容曝光率。
3. 利用 `wiki_page_evidence_refs` 的 Revision、准确引文、原文位置与 `content_chunk_id` 识别同源事实。
4. 实现血缘感知去重或配额：同一来源事实不能由原文和 Wiki 转述重复占满 top-k。
5. 默认保留一手原文优先和直接引用；Wiki 内容可用于导航、聚合或补充上下文，不能仅凭内容类型获得固定优势。
6. 覆盖 Wiki 更新、原文删除、重嵌入和索引失败时的一致性与回滚测试。

## Consequences

- MVP 范围更清晰，两条路径可以独立验证质量和故障域。
- `chunk_type='wiki_page'`、`wiki_page_id` 和 rerank 插件均不进入最终 schema 或验收标准。
- 共享 `content_chunks` 不等于融合召回：Wiki 页面仍不写入该表；证据表的可空 `content_chunk_id` 只表达生成血缘，不赋予 Wiki 内容任何 RAG 排序权重。
- 普通 RAG chat 不会自动召回 Wiki 页面；需要 Wiki 知识时，由 Agent 或调用方显式调用 `wiki_search`，待独立评测完成后再决定是否融合。
