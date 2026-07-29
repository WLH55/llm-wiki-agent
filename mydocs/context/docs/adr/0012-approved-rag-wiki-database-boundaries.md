# RAG/Wiki 数据库边界以逐表审批结果为准

> 状态：Accepted（2026-07-28）；摄取底座与表 1/2/7/11 的相关字段由 [ADR-0013](./0013-shared-content-chunk-substrate.md) 修订。

RAG 与 Wiki 共享 KB、Source、Document、不可变 Document Revision 以及 Active Revision 的 `content_chunks` 摄取底座，但保持独立的下游运行与检索数据面。启用向量检索时，新 Revision 先作为 `ready` 候选完成 embedding，再原子切换为 Active；embedding 失败时旧 Active Revision 继续服务。Wiki 按顺序完整消费激活后的共享 chunks；页面、wikilink、目录、文档来源和精确原文证据分别持久化。MVP 不保存跨运行 Map checkpoint，任务状态与进度归 `processing_runs` 和 `processing_spans`，Redis 只作为 RQ 队列后端。全部 15 张表的字段、约束、索引和生命周期以 [逐表审批 Spec](../../../specs/2026-07-27_数据库表逐表审批记录.md) 为唯一事实来源。

数据库不建立显式外键。所有逻辑引用必须由应用执行同租户/同 KB 校验、依赖顺序删除和孤儿巡检；设计与测试不得依赖数据库级联或外键错误。Wiki 证据以具体 Revision、准确引文和原文位置成立，`content_chunk_id` 是可清空的共享 chunk 快捷血缘，不能成为证据长期有效性的唯一依据。

本决策取代 ADR-0003 的页面内链接数组、物化目录路径和页面内溯源数组，取代 ADR-0007/0008 中冲突的 schema 字段，并取代 ADR-0004/0006 中对旧 Wiki 溯源字段的假设。ADR-0009 已由 ADR-0010 取代；未来启用 Wiki/RAG 融合必须基于独立评测另立 ADR。
