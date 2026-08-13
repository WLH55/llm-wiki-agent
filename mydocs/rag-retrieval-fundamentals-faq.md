# RAG 检索底层答疑：BM25、@@@、倒排索引、分词、稀疏向量

> 配套阅读：[p0-retrieval-cheatsheet.md](./p0-retrieval-cheatsheet.md)（一页速查表）、[rag-retrieval-parameters-explained.md](./rag-retrieval-parameters-explained.md)（参数详解）、[2026-08-06_17-43_RAG知识库检索设计.md](./specs/2026-08-06_17-43_RAG知识库检索设计.md)（P0 spec）
> 记录日期：2026-08-12
> 记录来源：P0 验收后对检索底层的系列问答

---

## Q1: `CREATE INDEX ... USING bm25` 这段 SQL 是什么意思？

```sql
CREATE INDEX IF NOT EXISTS content_chunks_bm25_idx
ON content_chunks
USING bm25 (id, kb_id, text, document_id, revision_id)
WITH (
    key_field = 'id',
    text_fields = '{"text": {"tokenizer": {"type": "chinese_lindera"}}}'
)
```

**一句话**：给 `content_chunks` 表建一个"全文搜索引擎"——把 `text` 列的每个词切出来建倒排索引，以后可以像搜索引擎一样搜"哪个块包含这些词、相关性多高"。

### 逐行拆解

| 片段 | 含义 |
|---|---|
| `CREATE INDEX IF NOT EXISTS content_chunks_bm25_idx` | 建索引，已存在则跳过 |
| `ON content_chunks` | 建在 `content_chunks` 表上 |
| `USING bm25` | **索引类型是 BM25**。类比：`USING btree`（排序查找）、`USING hnsw`（向量近似查找）、`USING bm25`（全文查找，pg_search 注册的新类型） |
| `(id, kb_id, text, document_id, revision_id)` | 参与索引的 5 列。**分工不同**：`text` 是"被全文索引的正文"；其他 4 列是快速列（fast fields），用于过滤（如 `kb_id = 2`）和直接取回，不用回表 |
| `key_field = 'id'` | 告诉 pg_search 主键是 `id`，内部靠它定位行 |
| `text_fields = '{"text": {...}}'` | 声明哪一列做全文索引，以及怎么切词 |
| `"tokenizer": {"type": "chinese_lindera"}` | **中文分词器**。建索引时把 `text` 内容按中文词组切开，每个词记进倒排索引 |

### 底层发生了什么（一次性建索引动作）

```
content_chunks 表里的每一行 text 内容
        ↓ chinese_lindera 分词
"向量检索使用 pgvector" → ["向量", "检索", "使用", "pgvector"]
        ↓ 建倒排索引
向量    → chunk 1, chunk 7
检索    → chunk 1, chunk 4, chunk 7
pgvector → chunk 1
        ↓
以后搜"向量检索" = 查倒排表，找出同时含这些词的块，算 BM25 分数排序
```

没有这个索引，`text` 就是一整块字符串，数据库只能做慢吞吞的 `ILIKE '%向量检索%'` 扫描（P0 之前就是这样，所以换掉了）。

---

## Q2: `@@@` 是什么？为什么是三个 @？

**`@@@` 是 pg_search（ParadeDB）定义的全文匹配运算符**。用法：

```sql
SELECT * FROM content_chunks WHERE text @@@ '向量检索';
```

意思是：`text` 列对 '向量检索' 做**全文搜索匹配**——pg_search 内部对查询词分词、查倒排索引、按 BM25 打分。

### 为什么是 `@@@` 而不是 `@@`

因为 `@@` 已被 Postgres 原生全文检索占用：

```sql
-- Postgres 原生（要手动 to_tsvector/to_tsquery，中文分词基本没用）
WHERE to_tsvector('english', text) @@ to_tsquery('english', 'vector');

-- pg_search 简化版（自动分词、自动查 BM25 索引）
WHERE text @@@ '向量检索';
```

ParadeDB 不想和官方语法冲突，就多打一个 `@`。

### 完整用法：`@@@` + `paradedb.score(id)` + 阈值子查询

`@@@` 只负责"匹配"，**打分要配合 `paradedb.score(id)`**：

```sql
-- 1. 先按相关性打分排序
SELECT id, paradedb.score(id) AS score
FROM content_chunks
WHERE kb_id = :kb_id AND text @@@ :query
ORDER BY score DESC
LIMIT 100;

-- 2. 阈值过滤（score < 0.3 的丢弃）——实际代码里用子查询包一层
SELECT * FROM (上面那个查询) sub
WHERE score >= 0.3
ORDER BY score DESC
LIMIT 20;
```

**关键规则**：`paradedb.score(id)` 只能在**引用了 BM25 索引的同一个查询**里调用，且要放在 `WHERE` 的子查询层——score 是查询时才算出来的，Postgres 不允许直接在 WHERE 里引用 SELECT 出来的别名。

### BM25 分数是什么

BM25 = 搜索引擎经典打分算法（Best Matching 25）：
> 查询词在文档里**出现越多次**分越高（会饱和）；**越罕见的词**权重越大；**文档越长**越要打折。

比如搜"向量检索"：一个块里 "向量" 出现 3 次 → TF 高加分；"检索"几乎每块都有 → IDF 低加不了多少分。实测分数 1.8~2.4 左右。

---

## Q3: 倒排索引里存的是 id 吗？

**是的，存的是 `key_field` 指定的列，我们设的是 `id`**（`content_chunks` 表主键）。

倒排索引真实结构类似：

```
term（词项）      → postings（posting list）
"向量"      → [ (id=1, tf=1), (id=7, tf=3) ]
"检索"      → [ (id=1, tf=1), (id=4, tf=2), (id=7, tf=1) ]
"pgvector"  → [ (id=1, tf=1) ]
```

posting 里除了 **id**，还附带统计量：**TF（该词在这行出现的次数）**、位置等——BM25 打分靠这些算。查"向量检索"时，取两条 posting list 求交集，按 BM25 公式算每个 id 的分数排序。

**为什么指定 `key_field='id'` 而不是默认**：Postgres 默认行定位器是 `ctid`（物理位置），随 `VACUUM` 变更不稳定。指定主键 `id` 后定位稳定，回表取 `document_id`/`text` 时直接 join 主键，干净利落。

---

## Q4: chinese_lindera 是怎么分词的？

**词典驱动的切词，发生在两个时机**：

| 时机 | 动作 |
|---|---|
| **写入时**（INSERT/UPDATE 行） | 每行的 `text` 被 tokenizer 切开，term 记入倒排索引 |
| **查询时** | 查询串被**同一个 tokenizer** 切开，再去倒排表找这些 term |

`chinese_lindera` 基于 **Lindera**（Rust 分词库，源自 MeCab 生态）的中文词典，算法是**词典 + 最长匹配**：

```
输入："向量检索使用 pgvector 的 halfvec"
  ↓ 从左到右扫，查词典找最长匹配
"向量" | "检索" | "使用" | "pgvector" | "的" | "halfvec"
```

- **词典里有的词**：切出来（"向量""检索""使用"）
- **词典里没有的词**：英文/数字按连续字母数字串整体作 token（"pgvector"、"halfvec"），单个汉字按单字处理
- **归一化**：英文统一小写等

**关键对称性**：写入和查询用**同一套 tokenizer**。不对称（写入分"向量检索"、查询分"向量"+"检索"）就匹配不上。pg_search 保证了两侧一致。

**和 jieba 的区别**：都是词典+统计分词，但实现不同（Lindera 是 Rust 版 MeCab 风格词典，jieba 是 Python）。ParadeDB 内置中文 tokenizer 只有 `chinese_lindera` 一个，无需自装插件。

---

## Q5: 稀疏向量和 BM25 是什么关系？

**核心一句话：BM25 是"打分算法"，稀疏向量是"实现方式"。BM25 可以不靠稀疏向量算（倒排索引直接算），稀疏向量也不一定装 BM25（可装 SPLADE 学习权重）。**

```
BM25（打分算法）
  ├── 实现方式 A：倒排索引直接算  ← pg_search、Elasticsearch 走这条路
  │      查 term → posting list → 现场用 BM25 公式算分
  │
  └── 实现方式 B：稀疏向量 + 内积  ← Milvus BM25、SPLADE 走这条路
         先把文档编码成稀疏向量，打分 = query稀疏向量 · doc稀疏向量
```

### 为什么内积能等价 BM25

BM25 分数可拆成"查询词权重 × 文档词权重"求和：

```
BM25(q, d) ≈ Σ_t  IDF(t) × TF_norm(t, d)

写成向量内积：
query_vec = [0, 0, idf(向量), idf(检索), 0, ..., idf(pgvector), 0]   ← 只在这几个词上有值
doc_vec   = [0, 0, tf_norm(向量), 0, 0, ..., tf_norm(pgvector), 0]   ← 只在这文档出现过的词上有值
分数 = query_vec · doc_vec     ← 内积 = 上面那个求和
```

所以"稀疏向量内积"和"BM25 公式"数学上等价。**倒排索引是另一种算同个求和的方式**——遍历 posting list，不构造完整向量。

### 什么时候必须用稀疏向量

**当你所在的系统"只有向量引擎、没有关键词引擎"时**，或想把关键词信号塞进向量流水线：

| 场景 | 为什么需要稀疏向量 |
|---|---|
| **Milvus/Qdrant 做混合检索** | 这些库没有内置 BM25 全文引擎，但支持 sparse vector 字段；编码成稀疏向量后，关键词检索=向量检索，代码统一 |
| **SPLADE / SPLADE-v2 学习式稀疏模型** | BERT 微调出"学习版 BM25 权重"（能处理同义词，BM25 做不到），输出天然是稀疏向量 |
| **单库多模态混合** | 在同一个向量库里同时做 dense（语义）+ sparse（关键词），统一运维、统一 API |
| **关键词分数参与向量重排** | sparse 分数和 dense 分数加权融合后再喂 reranker，需要两者都是"向量检索结果" |

**不需要稀疏向量的情况**：关键词引擎已有原生 BM25——pg_search、Elasticsearch、OpenSearch、SQLite FTS5。直接用 `@@@`/`match` 拿分数，多此一举编码稀疏向量只会增加复杂度。

### 对比总结

| 维度 | BM25 + 倒排索引（我们用的） | BM25 via 稀疏向量 |
|---|---|---|
| 存储 | 倒排表（term → id 列表 + TF） | 向量字段（词典维度，只存非零） |
| 打分 | 查询时现场算 BM25 公式 | 内积（数学等价） |
| 代表 | pg_search / Elasticsearch / FTS5 | Milvus BM25 function / SPLADE |
| 适合 | 有全文引擎的 PG 系架构 | 纯向量库架构、学习式稀疏模型 |
| 附加能力 | BM25 变体参数好调 | 可混入 dense 向量做向量库原生 hybrid |

**我们项目的现状**：pg_search 给 BM25 分数（标量）、pgvector 给余弦相似度（标量），两个标量在 RRF 里按**排名**融合——全程没有稀疏向量运算。WeKnora 在 Postgres 引擎下也和我们一样用 `paradedb.score`，只有用户选 Milvus 引擎时才走稀疏向量。

---

## Q6: 稀疏向量的"大词典"是怎么回事？

**是的，必须共享同一个全局大词典**，所有向量的维度对齐到同一张词表——否则内积没法算。

### 为什么必须共享词典

稀疏向量每个维度**对应一个固定词**。词典不一致就错位：

```
全局词典（唯一权威）：
  维度3 = "向量"   维度7 = "检索"   维度999 = "pgvector"   ...   共 100 万词

query_vec = [..., 维度3: idf(向量), 维度7: idf(检索), ..., 维度999: idf(pgvector), ...]
doc_vec   = [..., 维度3: tf(向量),   ...,           ..., 维度999: tf(pgvector), ...]
                        ↑                                            ↑
                 同一维度=同一个词，内积才有意义
```

词典不一致，比如 doc 里维度 3 是"向量"、query 里维度 3 是"苹果"，乘起来就是**张冠李戴的垃圾分数**。共享词典是稀疏向量成立的前提，不是可选项。

### 词典怎么来、怎么维护

| 方案 | 词典来源 | 特点 |
|---|---|---|
| **SPLADE 等学习式稀疏模型** | 训练时定死（BERT 词表，~3 万 token） | 词典固定，模型保证维度对齐，**没有扩展问题** |
| **BM25 式稀疏编码**（Milvus BM25 / 自建） | 随文档动态增长 | 新词 → 词典 +1 维 → **所有旧向量都要补一维 0**，麻烦 |

BM25 式词典动态增长正是工程痛点：每来一个没见过的词，全库向量维度 +1，旧数据要补零对齐（或靠哈希映射避免重写）。这也是为什么**没有全文引擎时才走稀疏向量**——倒排索引天然就是"动态词典"，加新词只是倒排表多一行，不用动已有数据。

### 和 dense 向量的关键区别

| | 稀疏向量 | dense 向量（我们用的 pgvector） |
|---|---|---|
| 维度含义 | 维度 = 词典里的词（有全局词表） | 维度 = 模型隐藏维度（无语义） |
| 维度数 | = 词典大小（几十万~几百万） | 固定（如 1024），模型输出定死 |
| 新词 | 词典 +1 维，旧向量补 0 | 不存在"新词"，模型自动编码 |
| 对齐 | **必须共享同一词典** | 同模型同维度即可内积 |

**我们系统的结论**：用 pg_search 倒排索引，从头到尾没有构造过稀疏向量，不存在词典对齐问题——pg_search 内部把"词典 → posting list"的管理全藏起来了。只有将来把关键词检索切到 Milvus/Qdrant 这类纯向量库，或上 SPLADE 时，才需要面对"共享词典 + 维度对齐"问题。
