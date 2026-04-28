将源文档导入 LLM Wiki。

用法：
- `/wiki-ingest raw/xxx.md` — 导入指定文件（含前置变更检测，未变更则跳过）
- `/wiki-ingest` — 无参数时扫描整个 raw/ 目录，批量处理所有变更文件

$ARGUMENTS 为空时走批量模式，否则走单文件模式。

---

## 单文件模式（$ARGUMENTS 为文件路径）

0. **前置变更检测** — 运行 `python tools/check_stale.py --scan --json` 获取文件状态：
   a. 在 JSON 输出的 `new` 列表中找到该文件 → 告知用户"新文件，将首次导入"，继续步骤 1
   b. 在 `updated` 列表中找到该文件 → 告知用户"文件已更新，将重新导入"，继续步骤 1
   c. 不在 `new` 也不在 `updated` 中（即未变更）→ 告知用户"文件未变更，跳过导入"，**结束**
   d. 在 `deleted` 列表中 → 告知用户"原始文件已丢失，无法导入"，**结束**

1. 读取给定路径的源文件
2. 读取 wiki/index.md 和 wiki/overview.md 获取当前上下文
3. 写入 wiki/sources/<slug>.md（按照 CLAUDE.md 中的源页面格式）
4. 更新 wiki/index.md — 在 Sources 部分添加新条目
5. 更新 wiki/overview.md — 如有必要则修订综合内容
6. 创建/更新关键人物、公司、项目的实体页面（wiki/entities/，必须包含 CLAUDE.md 规定的 frontmatter）
7. 创建/更新关键想法和框架的概念页面（wiki/concepts/，必须包含 CLAUDE.md 规定的 frontmatter）
8. 标记与现有知识库内容的任何矛盾
9. 追加到 wiki/log.md：## [今天的日期] ingest | <标题>
10. 运行 `python tools/check_stale.py --update-file <source_file>` 写入哈希缓存

完成所有写入后，总结：添加了什么内容，创建或更新了哪些页面，发现了哪些矛盾。

---

## 批量模式（$ARGUMENTS 为空）

1. **扫描变更** — 运行 `python tools/check_stale.py --scan` 获取三类文件：
   - 新增文件（raw/ 中存在但未导入 wiki）
   - 已更新文件（raw 文件哈希已变化）
   - 已删除文件（raw 文件丢失，wiki 页面孤立）

2. **报告状态** — 向用户展示扫描结果，告知有多少文件需要处理。如果没有变更，告知"无变更，所有文件均为最新"并结束。

3. **处理已删除文件** — 对每个已删除的 raw 文件：
   - 询问用户是否删除对应的 wiki 源页面
   - 如果用户同意，删除 wiki/sources/ 中的对应页面，并从 wiki/index.md 中移除条目

4. **批量导入** — 对每个新增文件和已更新文件，按顺序执行单文件模式的步骤 1-10：
   - 每完成一个文件后，告知用户进度（如 "2/5 已完成"）
   - 如果某个文件导入失败，记录错误并继续处理下一个

5. **汇总输出** — 完成后输出摘要：
   - 成功导入：N 个（列出文件名）
   - 跳过（未变更）：N 个
   - 删除孤立页面：N 个
   - 失败：N 个（列出错误原因）
   - 追加到 wiki/log.md：## [今天的日期] ingest-all | 导入 N 个，更新 N 个，删除 N 个
