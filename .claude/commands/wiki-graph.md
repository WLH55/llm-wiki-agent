构建 LLM Wiki 知识图谱。

用法：/wiki-graph

首先尝试运行：python tools/build_graph.py --open

如果失败且报错显示缺少依赖：

1. 先安装项目依赖：`pip install -e .`
2. 安装完成后重新运行：`python tools/build_graph.py --open`
3. 只有在重新运行后仍失败时，才手动构建图谱

手动构建图谱：

1. 使用 Grep 查找 wiki/ 中所有文件的 [[wikilinks]]
2. 构建节点列表：每个知识库页面一个节点，id=相对路径，label=标题，type 来自 frontmatter
3. 构建边列表：每个 [[wikilink]] 一条边，标记为 EXTRACTED
4. 推断 wikilink 未捕获的额外隐式关系 — 标记为 INFERRED 并附置信度分数（0.0-1.0）；低置信度的标记为 AMBIGUOUS
5. 写入 graph/graph.json，包含 {nodes, edges, built: 今天}
6. 写入 graph/graph.html 作为自包含的 vis.js 页面（按类型着色节点，按类型着色边，可交互，可搜索）

构建完成后，总结：节点数、边数、按类型分布、连接最多的节点（枢纽）。

追加到 wiki/log.md：## [今天的日期] graph | 知识图谱重建完成
