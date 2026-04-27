查询 LLM Wiki 并综合回答。

用法：/wiki-query $ARGUMENTS

$ARGUMENTS 是要回答的问题，例如 `主要主题有哪些？`

遵循 CLAUDE.md 中定义的查询工作流：
1. 读取 wiki/index.md 识别最相关的页面
2. 读取这些页面（最多约 10 个最相关的）
3. 对于命中的源页面（wiki/sources/），从其 frontmatter 的 source_file 字段找到 raw/ 中的原始文档，将原始内容也加入上下文
4. 综合出详细的 Markdown 答案，使用 [[PageName]] wikilink 引用
5. 在末尾包含 ## 来源 部分，列出所依据的页面
6. 询问用户是否要将答案保存为 wiki/syntheses/<slug>.md

如果知识库为空，告知用户并建议先运行 /wiki-ingest。
