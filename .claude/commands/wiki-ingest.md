将源文档导入 LLM Wiki。

用法：/wiki-ingest $ARGUMENTS

$ARGUMENTS 应为 raw/ 中的文件路径，例如 `raw/articles/my-article.md`

严格遵循 CLAUDE.md 中定义的导入工作流：
1. 读取给定路径的源文件
2. 读取 wiki/index.md 和 wiki/overview.md 获取当前上下文
3. 写入 wiki/sources/<slug>.md（按照 CLAUDE.md 中的源页面格式）
4. 更新 wiki/index.md — 在 Sources 部分添加新条目
5. 更新 wiki/overview.md — 如有必要则修订综合内容
6. 创建/更新关键人物、公司、项目的实体页面（wiki/entities/）
7. 创建/更新关键想法和框架的概念页面（wiki/concepts/）
8. 标记与现有知识库内容的任何矛盾
9. 追加到 wiki/log.md：## [今天的日期] ingest | <标题>

完成所有写入后，总结：添加了什么内容，创建或更新了哪些页面，发现了哪些矛盾。
