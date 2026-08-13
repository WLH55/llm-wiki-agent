# P0 检索地基 · 一页速查表

> 用途：上阵前 5 分钟过一遍。配套详细文档：[2026-08-06_17-43_RAG知识库检索设计.md](./specs/2026-08-06_17-43_RAG知识库检索设计.md) + [rag-retrieval-parameters-explained.md](./rag-retrieval-parameters-explained.md)

---

## 一句大白话

给知识库建了**两套索引**——一套"懂意思"（向量）、一套"认字面"（BM25 关键词），查的时候两路一起搜、加权融合、补齐上下文，让后面的 LLM 能更准地找到答案片段。

---

## 核心概念 / 规则 / 公式（短条目）

### 三块拼图
- **pgvector**：向量检索。halfvec 半精度 + HNSW 索引，算余弦相似度。语义相近就命中（换句话也能懂）。
- **pg_search**（ParadeDB）：BM25 关键词检索。`text @@@ :query` + `paradedb.score(id)` 打分。**分词器 = chinese_lindera**（ParadeDB 内置中文分词，正确切中文词）。字面包含就命中（专有名词、代码、型号最准）。
- **RRF**：把两路结果融合成一张榜。公式：`score = 0.7/(60 + rank_v) + 0.3/(60 + rank_k)`（k=60，向量 7 成、BM25 3 成；某路没命中该路贡献为 0）。

### 关键参数（settings 默认值）
| 参数 | 值 | 作用 |
|---|---|---|
| 向量阈值 | 0.15 | 相似度低于它直接丢（宁多勿漏） |
| BM25 阈值 | 0.3 | 分数低于它直接丢（关键词匹配更硬） |
| 过检索 | clamp(limit×5, 50, 500) | 数据库多查候选，融合后再截断 |
| RRF k / 权重 | 60 / 0.7:0.3 | 排名融合的平滑常数和权重 |

### 检索流程（search() 编排，6 步）
1. 查询文本 → embedding
2. **向量路** + **BM25 路** 并行检索（各过检索到 50~500 候选）
3. 各自阈值过滤
4. **RRF 融合** → 按融合分降序
5. 截断到 limit（默认 5）
6. **nearby 增强**：top-N 每条补 `chunk_index ± 1` 两个相邻块进 `context` 字段

### 其他要点
- **match_type** 四种：`vector` / `bm25` / `rrf`（融合榜）/ `nearby`（相邻块）
- **embedding 降级**：嵌入 API 挂了（Key 失效/超时）→ 自动降级纯 BM25 检索，不报错
- **标题前缀**：新文档嵌入输入 = `文档标题 + \n + chunk.text`（帮助向量检索理解上下文；旧数据不重索引）
- **RetrievalResult**：检索统一数据结构，12 个字段（含 citation_id，P1 引用回链用）
- **代码位置**：检索逻辑在 `backend/app/knowledge_bases/service/retrieval.py`；旧 `search/` 模块已删
- **pg_search 必须**在 `shared_preload_libraries` 加载 → 改配置后要**重启 postgres 容器**

---

## 3-5 个真实场景

1. **换句话问**："如何配置向量检索" vs 原文"pgvector 的 halfvec 配合 HNSW 索引"——BM25 命中不了"配置"，向量路靠语义命中，RRF 里排前。
2. **专有名词锁死**：问 "ParadeDB 的 pg_search 扩展"——BM25 路精准命中含这些词的块，向量路可能跑偏，RRF 互补。
3. **Jina Key 失效**：向量路失败 → 自动降级纯 BM25，用户无感，答案照样有（只损失语义召回）。
4. **跨块上下文**："高温下带宽多少"命中块 4，nearby 把块 3（正常 10Gbps）和块 5（温度范围）一起给 LLM，它才答得完整。
5. **问没收录的东西**：两路都空 → 返回 0 条 → P1 的 chat API 会直接回固定话术"知识库中无法回答"，不浪费 LLM 调用。

---

## 新手最容易犯的错 / 混淆点

1. **混淆 OVER_RETRIEVE 和 TOP_K**：过检索 = 数据库多查多少条（池子大小）；TOP_K = 融合前每路截断多少。前者是"多捞"，后者是"少取"。
2. **觉得向量阈值 0.15 太低**：故意的。召回阶段宁多勿漏，让 RRF 去筛；阈值只是垃圾线，不是质量线。
3. **拿 RRF 分数当相似度比较**：RRF 分数是排名融合分（~0.01 量级），**只能在同一查询内比大小**，不能跨查询比较，更不能当置信度展示。
4. **改完 compose 不重启容器**：`shared_preload_libraries=pg_search` 只在启动时读，不重启会报 `pg_search must be loaded via shared_preload_libraries`。
5. **以为换 ParadeDB 镜像要清数据卷**：不用。ParadeDB 就是加了扩展的 PG16，直接挂原数据目录，数据无损。
6. **在 SQL 里手写 `@@@` 忘写阈值子查询**：BM25 查询要 `paradedb.score(id) >= :threshold` 子查询过滤，否则低分垃圾全进来。
7. **改检索逻辑去动 API 层**：检索是内部 service（供 P1 SearchPlugin 调用），对外接口由 P1 chat API 承担，现在没有对外检索端点。

---

## 上场前检查清单

- [ ] `docker ps` 里 postgres 容器是 `paradedb/paradedb` 镜像且 healthy
- [ ] `SELECT extname FROM pg_extension` 有 `vector` + `pg_search` 两行
- [ ] `alembic current` = 003（BM25 索引已建）
- [ ] `pg_indexes` 里 `content_chunks_bm25_idx` 存在（USING bm25 + chinese_lindera）
- [ ] settings 里 7 个 RAG 参数值符合预期（0.15 / 0.3 / 5x50-500 / 0.7:0.3）
- [ ] `pytest tests/test_search.py` 全绿（service 层行为契约测试）
- [ ] 有 embedding API 可用（否则只会走降级 BM25，向量语义失效）

---

## 快问快答（自测 5 题）

1. **Q**：RRF 融合公式是什么？**A**：`0.7/(60+rank_v) + 0.3/(60+rank_k)`，k=60。
2. **Q**：BM25 索引用什么中文分词器？**A**：`chinese_lindera`（ParadeDB 内置）。
3. **Q**：向量阈值和 BM25 阈值各是多少，为什么 BM25 更高？**A**：0.15 vs 0.3；关键词匹配天然更硬，低分=只命中无关词。
4. **Q**：embedding API 挂了会发生什么？**A**：search() 自动降级为纯 BM25 检索，不报错。
5. **Q**：nearby 增强是什么，补在哪？**A**：top-N 每条命中块的 `chunk_index ± 1` 两个相邻块，塞进结果的 `context` 字段。
