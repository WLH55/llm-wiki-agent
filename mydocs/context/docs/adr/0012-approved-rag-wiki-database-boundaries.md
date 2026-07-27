# RAG/Wiki 数据库边界以逐表审批结果为准

> 状态：Accepted（2026-07-28）

RAG 与 Wiki 共享 KB、Source、Document 和不可变 Document Revision，但保持独立数据面：`content_chunks` 只保存 Active Revision 的 RAG 检索分块；Wiki 长文使用任务内临时分段，页面、wikilink、目录、文档来源和精确原文证据分别持久化。全部 15 张表的字段、约束、索引和生命周期以 [逐表审批 Spec](../../../specs/2026-07-27_数据库表逐表审批记录.md) 为唯一事实来源。

数据库不建立显式外键。所有逻辑引用必须由应用执行同租户/同 KB 校验、依赖顺序删除和孤儿巡检；设计与测试不得依赖数据库级联或外键错误。Wiki 证据以具体 Revision、准确引文和原文位置成立，`rag_chunk_id` 仅为 MVP 始终为空的未来融合快捷关联。

本决策取代 ADR-0003 的页面内链接数组、物化目录路径和页面内溯源数组，取代 ADR-0007/0008 中冲突的 schema 字段，并取代 ADR-0004/0006 中对旧 Wiki 溯源字段的假设。ADR-0009 已由 ADR-0010 取代；未来启用 Wiki/RAG 融合必须基于独立评测另立 ADR。
