# 区分队列自动重试与业务处理重跑

> 状态：Accepted（2026-07-29）

RQ 对同一 Job 的自动重试沿用同一条 `processing_runs` 记录，因为它只是同一业务处理意图的再次执行，不是用户可独立识别的新任务。自动重试等待期间 Run 从 `running` 回到 `pending` 并清空心跳，重新执行后回到 `running`；重试预算耗尽才进入 `failed`。只有用户或系统对终态 Run 发起业务重跑时才创建新 Run，并通过 `retry_of_run_id` 与 `attempt_no` 保存重跑链。这样既保留终态历史，又避免短暂网络错误或 Worker 重启制造大量 Run 记录。
