# MVP Wiki/RAG 独立运行

> 状态：Accepted（2026-07-27）<br>
> 取代：[ADR-0009](./0009-retrieval-architecture.md) 中“Wiki 页面在 MVP 写入 `content_chunks` 并固定加权 1.3”的决策。
> 修订：2026-07-27 逐表审批取消 `content_chunks.chunk_type` / `wiki_page_id` 融合预留；未来融合必须另立 ADR 与 migration。

## Context

参考项目的源码并没有实现 Wiki 页面写入 RAG chunk 的链路：`ChunkTypeWikiPage`、删除逻辑和 WikiBoost 插件存在，但缺少任何对应的 upsert/写入端。因此，源码能证明“曾有融合意图且实现未闭环”，不能证明当前的双路径分离是经过明确取舍后的最终设计。

同时，Wiki 页面由原始文档 chunk 经 LLM 综合生成。若原文 chunk 与派生 Wiki 内容直接进入同一召回池，同一事实可能以两种表述重复占用 top-k；固定的 Wiki boost 还可能让二手转述压过一手原文，增加幻觉和溯源风险。

## Decision

MVP 同时完成两条能力闭环，但数据面和召回面保持独立：

- `knowledge_search` 只检索原始文档派生的 `content_chunks`，MVP 写入端只产出 `chunk_type='document'`（以及后续明确启用的原始材料类型）。
- `wiki_search` 只检索 `wiki_pages`，不触发 Wiki 页面切块、embedding 或 `content_chunks` 写入。
- 不启用 WikiBoost，不在 RAG 结果中对 `wiki_page` 做 1.3 倍或其他固定加权。
- `vector_enabled` / `keyword_enabled` 控制 RAG 路径，`wiki_enabled` 控制 Wiki 生成与独立检索；同时开启表示“两条能力都可用”，不表示结果已融合。
- MVP 不做跨路径联合排序、自动混合 top-k 或 query 级手动模式开关；调用方显式选择 `knowledge_search` 或 `wiki_search`。

## Schema 边界

`content_chunks` 只保存当前生效 Document Revision 的 RAG 分块，不保留 `chunk_type`、`wiki_page_id` 或其他 Wiki 融合字段。Wiki 血缘由独立的 `wiki_page_document_refs` 与 `wiki_page_chunk_refs` 表表达；如果未来评测证明需要融合，必须另立 ADR 并显式增加 schema 与写入链路。

## 融合启用门槛

完成 Wiki 与 RAG 两条独立路径后，只有满足以下条件才另立 ADR 讨论融合：

1. 使用同一批真实查询分别评估 RAG-only、Wiki-only，建立 Recall@K、nDCG/MRR、引用正确率和答案忠实度基线。
2. 明确融合目标是提升答案质量，而不是仅提高 Wiki 内容曝光率。
3. 利用 `wiki_pages.chunk_refs` 建立派生 Wiki 内容到原始 chunk 的血缘映射。
4. 实现血缘感知去重或配额：同一来源事实不能由原文和 Wiki 转述重复占满 top-k。
5. 默认保留一手原文优先和直接引用；Wiki 内容可用于导航、聚合或补充上下文，不能仅凭内容类型获得固定优势。
6. 覆盖 Wiki 更新、原文删除、重嵌入和索引失败时的一致性与回滚测试。

## Consequences

- MVP 范围更清晰，两条路径可以独立验证质量和故障域。
- `chunk_type='wiki_page'`、`wiki_page_id` 和 rerank 插件均不进入最终 schema 或验收标准。
- schema 不为未经评测的未来融合承担预留字段成本；未来启用融合时接受显式 migration。
- 普通 RAG chat 不会自动召回 Wiki 页面；需要 Wiki 知识时，由 Agent 或调用方显式调用 `wiki_search`，待独立评测完成后再决定是否融合。
