# WeKnora RAG 系统设计调研报告

> 调研对象：`D:\AI\WeKnora-feat_MCP`（Go 项目，`github.com/Tencent/WeKnora`）
> 调研方法：5 个并行只读子代理分阶段调研，全部附 file:line 证据
> 调研日期：2026-08-11

## 整体架构

双流水线架构，`chunks` 表是唯一事实来源，向量库和 BM25 索引都是派生副本。

```
摄入流水线(asynq异步): DocReader -> Chunking -> 落库 -> 向量化 -> 多模态 -> PostProcess 4并行扇出
检索+生成流水线(chat_pipeline事件驱动): QUERY_UNDERSTAND -> CHUNK_SEARCH_PARALLEL -> CHUNK_RERANK -> CHUNK_MERGE -> FILTER_TOP_K -> INTO_CHAT_MESSAGE -> CHAT_COMPLETION_STREAM
```

## 一、数据准备阶段

### 1.1 文档加载与清洗

**多引擎可插拔**（`knowledge_process.go:3629` resolveDocReader）：simple(Go原生)/builtin(Python gRPC)/markitdown/mineru/paddleocr_vl/opendataloader/weknoracloud。超时保护 30 分钟（`knowledge_process.go:3582`）。

**扫描件 OCR 分阶段架构**：docreader 不执行 OCR，只检测扫描页(图像覆盖率>=50%, `pdf_parser.py:76`)并渲染 JPEG；OCR 由 Go 侧 `ImageMultimodalService.Handle`(`image_multimodal.go:137`) 异步执行，扫描件用专用 prompt；OCR 文本经 `sanitizeOCRText`(`ocr_sanitizer.go:29`) 清洗。

**版式**：PDF 几何 XY-cut 算法重排阅读顺序(`pdf_parser.py:99`)，页眉页脚去重(`pdf_parser.py:1271`)。**表格**：`protectedPatterns`(`chunker/splitter.go:118`) 保护 Markdown 表格不被切断。

**元数据**：提取 page_count/scanned_page_count/image_source_type(`pdf_parser.py:1553`)，不提取作者。

### 1.2 文本分块

**三层策略链**(`chunker/strategy.go:198`)，不合格自动降级：auto(profiler自动选)/heading(标题感知)/heuristic(启发式)/recursive(递归)。默认 ChunkSize=512 Overlap=80。

**父子分块(small-to-large)**：父分块(~1024词)写 chunks 表(chunk_type=parent_text)不进向量库；子分块(~256词)写 chunks 表(chunk_type=text, parent_chunk_id 指向父)进向量库。召回子分块后查 parent_chunk_id 返回父分块作上下文。证据: `knowledge_process.go:541`。

**ContextHeader 面包屑**(`heading_splitter.go:72`)：每个块携带章节层级路径。句子窗口检索未实现。

### 1.3 元数据增强

chunks 表有 metadata JSONB 字段(`000000_init.up.sql:179`)，存 DocumentChunkMetadata/FAQChunkMetadata，可用于硬性过滤。

## 二、索引构建阶段

### 2.1 嵌入模型

多 Provider 抽象(`embedder.go:16`)：Ollama/OpenAI/Aliyun/Volcengine/Jina/Azure/NVIDIA/Gemini/智谱/WeKnoraCloud。默认 bge-m3(1024维)。未实现 query/passage task 区分(对称模型)。向量表 `embedding halfvec` + `dimension INTEGER` 支持多模型混存(`000002_embeddings.up.sql:23`)。

### 2.2 向量数据库

11 引擎可插拔(`types/retriever.go:8`)，双轨制：env-store(postgres/sqlite 由 RETRIEVE_DRIVER 派生) + DB-store(milvus/es 等入 vector_stores 表)。KB 通过 vector_store_id 绑定(`000036`)。全用 HNSW，pgvector halfvec 半精度。批量离线写入(batchSize=40 并发上限5)。

### 2.3 GraphRAG

生产用 `extract.go` 的 ChunkExtractService(asynq 异步, 按 chunk 粒度 LLM 抽取)，graph.go 的 graphBuilder 无调用方。存储在 chunks 表(chunk_type=entity/relationship)，无独立图表。图谱参与检索: search_parallel.go 中 chunk 与 entity 检索并行。未发现图谱质量控制机制。

## 三、检索优化阶段

### 3.1 查询重构

**LLM 查询重写**(`query_understand.go`)：加载历史做指代消解+省略补全，输出 JSON {rewrite_query, intent, image_description}。9 类意图(`types/chat_manage.go:83`)决定"是否检索"。

**本地查询扩展**(`query_expansion.go`)：低召回兜底(非LLM, jieba分词+停用词去除)，阈值降低x0.8，TopK翻倍。

未实现: multi-query 分解、step-back prompting、HyDE。

### 3.2 查询路由

基于 KB 配置的静态分区(`knowledgebase_search.go:317`)，非 LLM 路由。三向分区: FAQ向量/文档向量/文档关键词。FAQ 硬编码排除关键词索引(行347)。多存储扇出: errgroup 并发上限4组 30s超时 all-or-nothing。

### 3.3 混合检索与融合

**BM25 多引擎各异**：ES/OpenSearch 原生 BM25；SQLite FTS5 bm25()；Milvus BM25+sparse；Postgres 未发现 pg_search/ParadeDB。

**RRF 融合**(`knowledgebase_search_fusion.go:84`)：`score = vectorWeight/(k+vectorRank) + keywordWeight/(k+keywordRank)`，k=60，权重默认 0.7:0.3。

**分数归一化**(`normalizer.go:105`)：仅归一化向量分数，BM25 原样透传(RRF 基于排名免疫尺度)。

**过检索**：`max(topK*5, 50) * len(kbIDs)` 上限500。**阈值**：向量0.15/0.2，关键词0.3。

### 3.4 重排序

Cross-encoder 多 Provider(`reranker.go:14`)。核心逻辑(`rerank.go`)：Passage清洗(剥离markdown)+增强(合并Content+ImageInfo+Questions) -> 阈值过滤+降级 -> 复合分数(0.6*model+0.3*base+0.1*source) -> MMR去冗余(lambda=0.7 Jaccard) -> FAQ加分。

上下文压缩: 无独立LLM压缩，通过 Merge 去重+部分重叠去除(token overlap>=0.85)。

### 3.5 CRAG

未实现。无检索评估器/自我反思循环。有 web_search.go 可补充外部信息(意图分类触发，非CRAG)。

## 四、生成集成阶段

### 4.1 双生成路径

- **chat_pipeline**(插件化, 单轮RAG)：事件驱动 Plugin+EventManager，10步流水线
- **Agent Runtime**(`internal/agent/`, ReAct多轮)：`engine.go:348` executeLoop，支持原生 Function Calling(`observe.go:451`)

### 4.2 提示工程

系统Prompt(`system_prompt.yaml:18`)要求严格基于上下文、禁止使用先验知识。"不知道"兜底(`session_knowledge_qa.go:762`)：三级(LLM/固定话术/模型)。上下文渲染为XML结构化(`<documents>`+`<context id="N">`)。

### 4.3 引用回链(双层句柄系统)

1. 注册: `registry.go:215` 为每个 chunk 分配私有短句柄 cN
2. 编码: chunk_id 替换为 cN 注入模型
3. 模型输出 `<ref id="cN"/>` 内联标注
4. 解码: `citations.go:169` ExpandText 还原为 `<kb doc="标题" chunk_id="原始ID" />`
5. 安全: CompactPublicCitations 防历史 chunk ID 泄漏给模型

### 4.4 流式输出

SSE 流式返回(`chat_completion_stream.go:39`)，引用流中实时展开(`citations.go:193`)。

## 五、评估与可观测性阶段

### 5.1 RAG 三元组

**未实现** RAG Triad。实现传统指标: 检索侧(Precision/Recall/NDCG/MRR/MAP, `evaluation.go:83`) + 生成侧(BLEU/ROUGE, `evaluation.go:94`)。

### 5.2 评估工具链

自研 Go 原生(`metric/` 目录)，未集成 RAGAS/LlamaIndex。评估数据集 Parquet 格式(MS MARCO 风格, `dataset/samples/`)。评估触发: 生产 API(POST /api/v1/evaluation Admin权限)，走真实 RAG pipeline，结果存内存(进程重启丢失)。

### 5.3 可观测性

**DB Span**(`knowledge_span_tracker.go`)：4种 span_type(root/stage/subspan/generation)，5阶段(docreader/chunking/embedding/multimodal/postprocess)，6状态，级联取消，GORM 持久化。

**Langfuse 集成**(`internal/tracing/langfuse/`)：基于 OpenTelemetry SDK，OTLP/HTTP 导出。覆盖 HTTP+Asynq 中间件+业务代码，跨进程 traceparent 传播。**检索侧有完整 tracing**(retrieve span/rerank span/QA pipeline spans)。未集成 Arize Phoenix。

### 5.4 搜索日志

**无 search_log 表**。搜索结果不写持久化日志。有"建议问题反馈"(impression/click/dismiss)但不是搜索结果反馈。

### 5.5 审计日志

5大类操作(rbac/vector_store/opensearch/system/kb)，append-only，配置驱动保留时长，24h清理间隔，denied操作1分钟滑动窗口去重。

## 六、三方对照表

| 阶段 | 子环节 | WeKnora | 本项目现状 |
|---|---|---|---|
| 数据准备 | 文档加载 | 多引擎+分阶段OCR | 15+格式, 无页码到chunk |
| | 分块 | 三层策略链+父子+ContextHeader | 仅句号切分, 策略字段未兑现 |
| | 元数据 | metadata JSONB | 无metadata字段 |
| 索引构建 | 嵌入 | 10+Provider, bge-m3 | Jina v5 1024维 |
| | 向量库 | 11引擎可插拔双轨制 | pgvector halfvec HNSW |
| | GraphRAG | extract.go 生产路径 | 未实现 |
| 检索优化 | 查询重构 | LLM重写+意图+本地扩展 | 未实现 |
| | 路由 | KB配置静态三向分区 | 仅mode=rag/wiki |
| | 混合检索 | 多引擎BM25+加权RRF | BM25退化为ILIKE |
| | Rerank | Cross-encoder+MMR+复合分数 | 未实现(空目录) |
| | CRAG | 未实现 | 未实现 |
| 生成集成 | Prompt | 严格上下文+兜底+XML渲染 | 无LLM生成调用 |
| | 引用回链 | 双层句柄系统 | 未实现 |
| | 结构化输出 | Function Calling(Agent) | 未实现 |
| 评估可观测 | RAG三元组 | 未实现(传统指标) | 未实现 |
| | Tracing | Langfuse+DB Span双层 | 仅摄入侧DB Span |
| | SearchLog | 无 | 表建了未接入 |
