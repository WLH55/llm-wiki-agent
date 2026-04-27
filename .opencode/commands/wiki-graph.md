构建 LLM Wiki 知识图谱。

用法：/wiki-graph

步骤：

1. 运行机械提取：`python tools/build_graph.py`
   - 从 wiki 页面构建节点
   - 提取 [[wikilinks]] 作为 EXTRACTED 边
   - 保留 graph.json 中已有的 INFERRED/AMBIGUOUS 边
   - 输出 graph/graph.json + graph/graph.html

2. 读取 graph/graph.json，查看所有节点和已提取的边

3. 对每个节点进行语义推断 — 识别 wikilink 未捕获的隐式关系：
   - 查看节点的 preview 内容和类型
   - 判断该节点与哪些其他节点存在语义关联
   - 为每条推断边标注 relationship（一行描述）和 confidence（0.0-1.0）
   - confidence >= 0.7 标记为 INFERRED，< 0.7 标记为 AMBIGUOUS

4. 将推断的边追加到 graph/graph.json 的 edges 数组中，格式：
   ```json
   {
     "id": "from->to:INFERRED",
     "from": "page-id",
     "to": "page-id",
     "type": "INFERRED",
     "title": "关系描述",
     "label": "",
     "color": "#C4956A",
     "confidence": 0.8
   }
   ```

5. 重新运行 `python tools/build_graph.py` 重新生成 graph.html（会保留刚写入的推断边）

6. 如果用户加了 `--open`，运行 `python tools/build_graph.py --open`

构建完成后，总结：节点数、边数（按类型分布）、连接最多的节点。
追加到 wiki/log.md：## [今天的日期] graph | 知识图谱重建完成
