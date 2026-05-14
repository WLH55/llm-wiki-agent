刷新过期的 wiki 来源页面。

用法：/wiki-refresh $ARGUMENTS

可选参数：
- （无参数）— 仅刷新有变更的来源
- `--force` — 强制将所有来源标记为过期

遵循以下工作流：

1. 运行 `python tools/check_stale.py` 检测哪些原始文档有变更（基于 SHA-256 哈希对比）
2. 如果输出"所有来源页面均为最新"，告知用户并结束
3. 对每个过期来源，重新执行 AGENTS.md 中定义的导入工作流：
   - 读取 raw/ 原始文档
   - 读取 wiki/index.md 和 wiki/overview.md 获取当前上下文
   - 重写 wiki/sources/<slug>.md
   - 更新 wiki/overview.md（如有必要）
   - 更新/创建实体和概念页面
   - 标记矛盾
   - 追加到 wiki/log.md
4. 所有过期来源刷新完成后，运行 `python tools/check_stale.py --update` 更新哈希缓存
5. 输出刷新摘要：刷新了几个、跳过了几个

追加到 wiki/log.md：## [今天的日期] refresh | 刷新了 N 个过期来源页面
