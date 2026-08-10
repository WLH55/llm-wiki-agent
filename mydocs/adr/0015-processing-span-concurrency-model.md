# Processing Span 不保存全局执行序号

> 状态：Accepted（2026-07-29）

`processing_spans` 使用 `pending/running/succeeded/failed/skipped/cancelled` 表达阶段生命周期，并允许未开始的 Span 使用空 `started_at`。表中不保存 `sequence_no`：并行阶段争抢全局序号会增加写入协调，而且序号容易被误当成依赖关系。固定阶段的展示顺序来自应用阶段注册表，依赖关系来自编排代码，嵌套关系来自 `parent_span_id`，同级动态 Span 按 `created_at, id` 稳定排序。
