查询 LLM Wiki 并综合回答。

用法：/wiki-query $ARGUMENTS

$ARGUMENTS 是要回答的问题，例如 `主要主题有哪些？`

遵循 CLAUDE.md 中定义的查询工作流：
1. 读取 wiki/index.md 识别最相关的页面
2. 读取这些页面（最多约 10 个最相关的）
3. 综合生成一份详尽的 Markdown 答案，使用 [[页面名称]] 形式的 Wiki 链接进行引用；
4. 在答案末尾添加 ## 来源 部分，列出你所引用的所有页面；
5. 询问用户是否需要将此答案保存为 wiki/syntheses/<slug>.md 文件。

如果知识库为空，告知用户并建议先运行 /wiki-ingest。
