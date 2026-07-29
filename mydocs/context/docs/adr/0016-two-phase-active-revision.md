# 启用向量检索时两阶段激活 Document Revision

> 状态：Accepted（2026-07-29）

新 Document Revision 完成共享解析和分块后先成为 `ready` 候选，而不立即替换 `documents.active_revision_id`。未启用向量检索时可以直接激活；启用时必须先为整套候选 chunks 成功写入 embedding，再在一个事务中切换 Active Revision、清空旧 chunk 快捷证据关联并删除旧 chunks。这样 embedding 失败时旧 Active Revision 和旧向量继续服务，避免出现新文本已经生效但向量召回不可用的半激活状态。Wiki 生成不是激活门槛，只消费激活后的 Chunk Set，其失败不回滚激活。
