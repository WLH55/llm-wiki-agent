# RAG/Wiki 共享 Active Revision 的内容分块底座

> 状态：Accepted（2026-07-28）

Document Revision 只执行一次标准解析与分块，并将完整结果持久化为 `content_chunks`。在线 RAG 与 Wiki 都消费同一 Active Chunk Set；启用向量检索时，`rag_index` 先处理候选 Chunk Set，成功后候选才原子激活。RAG 负责 embedding、BM25/向量索引和 `knowledge_search`，Wiki 在激活后负责 Map/Reduce、页面、链接与证据。Wiki 页面本身永不写入 `content_chunks`，因此共享摄取不等于融合召回。

选择共享底座，是因为两条路径需要读取同一份原文并保留相同页码、段落和字符定位。重复解析和分块会增加计算、产生边界漂移，并让 Wiki 证据难以稳定映射回 RAG 展示的原文块。共享 chunks 让解析结果可审计、失败后可复用，也允许 `wiki_page_evidence_refs.content_chunk_id` 在 chunk 存活期间直接回到生成输入；证据的长期有效性仍由 `revision_id`、`evidence_quote` 和 `source_locator` 保证。

## Considered Options

- 两条路径独立解析、Wiki 只保存 Redis 临时分段：实现边界直观，但重复计算，分段可能漂移，Redis 丢失后必须重新解析，证据审计更复杂，因此不采用。
- 完全照搬 WeKnora 的长文组装或截断方式：复用程度高，但无法保证 Wiki 覆盖完整文档，也不满足本项目的精确证据要求，因此不采用。
- 新增第 16 张共享解析块表，再由 RAG 复制到 `content_chunks`：边界最纯粹，但引入重复正文、同步和清理成本；当前共享原文块与 RAG 召回粒度一致，没有足够收益，因此不采用。

## Consequences

- 共享分块配置属于 `knowledge_bases`；`kb_rag_configs` 只保留 RAG 启停、召回方式和 embedding 配置。
- `processing_run_id` 记录创建 chunk 的共享解析 Run；`embedding_run_id` 记录最后写入 embedding 的 RAG Run。除 embedding 相关字段外，RAG 不得原地修改 chunk 内容。
- Wiki 按 `chunk_index` 遍历全部 chunks，并将相邻 chunks 确定性组合成 token 预算内的 Map 批次。MVP 的 manifest 与 Map 结果只存在于当前 Worker 内存；Redis 只作为 RQ 队列后端，不保存业务进度或 Map 结果。
- 缺块、重复序号或顺序不一致会使 Wiki 任务显式失败；Wiki Worker 不得自行重解析原文件来掩盖共享摄取故障。
- 共享解析失败会同时阻塞 RAG 与 Wiki。启用向量检索时，候选 embedding 失败会阻止新 Revision 激活，但旧 Active Revision 继续同时服务 RAG 与 Wiki；激活后的 Wiki 生成失败不回滚新 Active Revision。
- Wiki-only 的 KB 也会产生 `content_chunks`，因此 chunk 正文仍进入物理 BM25 索引；在线 `knowledge_search` 是否可用继续由 RAG 配置控制。
- 激活事务删除旧 Active Revision 的 chunks 前，应用先清空证据表中匹配的 `content_chunk_id`；精确引文、位置和 Revision 引用继续保留。被更新候选取代或所属文档删除的非 Active chunks 由应用物理清理。
