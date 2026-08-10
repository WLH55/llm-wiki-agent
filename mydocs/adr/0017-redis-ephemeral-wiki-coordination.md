# Redis 只承担 Wiki 可丢失的短期协调

> 状态：Accepted（2026-07-29）

Redis 除作为 RQ 队列后端外，还用于两类不承载业务事实的短期协调：同一 KB 的 Wiki 生成租约锁 `wiki:lock:{tenant_id}:{kb_id}`，以及文档删除墓碑 `wiki:deleted:{tenant_id}:{kb_id}:{document_id}`。租约值必须包含 `run_public_id` 与本次执行的随机 token；获取使用带 TTL 的 `SET NX`，续租和释放必须通过 Lua 先核对 token，锁冲突时 Run 保持 `pending` 并延迟重试，续租失败或失去所有权的 Worker 必须丢弃本次内存结果。删除墓碑的 TTL 必须长于 Wiki Job 最大运行时间，用于让排队中或执行中的 Worker 尽早停止。

Redis 锁和墓碑均允许因重启、驱逐或 TTL 到期而丢失，不保存 manifest、阶段进度、Map/Reduce 结果或任何唯一业务副本。最终提交仍必须在同一 PostgreSQL 事务中校验 KB、Document 与 Revision 未删除、目标 Revision 仍为 Active、Run 仍为 `running`，并使用 `wiki_pages.version` 乐观锁防止页面覆盖；任一条件不成立时整体回滚。该方案不新增表字段，也不增加 `processing_runs` 的运行中唯一索引。
