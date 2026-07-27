# 三套边并存模型（链接图 + 目录树 + 溯源）

> 状态：Schema 细节已由 [ADR-0012](./0012-approved-rag-wiki-database-boundaries.md) 取代（2026-07-28）。<br>
> 本文保留“三类关系必须分离”的历史决策；页面内链接数组、物化目录路径、页面内溯源数组和显式外键均不再采用。

llm_wiki3.0 的 wiki 页面之间不存在"一种统一的关系"，而是**三套边服务三种用途并存**：

- **链接图边**：从 markdown `[[xxx]]` 正则抽取，双向冗余存 `pages.in_links` / `pages.out_links` 数组，**无类型、无权、有向**。
- **目录树边**：`pages.folder_id`（source of truth）+ `pages.parent_slug`（可选语义父）+ `wiki_folders` 邻接表；`category_path`/`depth`/`wiki_path` 是物化路径缓存。
- **溯源边**：`pages.source_refs`（文档级 `<kb_id>|<doc_title>`）+ `pages.chunk_refs`（chunk UUID 级）。

页面类型共 7 种：自动生成 5 种（`summary` / `entity` / `concept` / `index` / `log`）+ Agent 手建 2 种（`synthesis` / `comparison`）。

## Context

PRD v4.2 US 11 原本想"8 种语义边（如 `related_to` / `sub_of` / `instance_of` / `derived_from` 等）"。但：

1. **LLM 抽取边类型不可靠**：业界实践（含参考项目 WeKnora）证明，让 LLM 在抽实体时同时给边分类，**70%+ 的边会被打成 `related_to` 兜底**——精心设计的 7 种语义边被淹没。`related_to` 实际是语义垃圾桶。
2. **参考项目实践已证伪**：WeKnora（参考路径见下）原本也考虑过类型化边，但落地时选择了无类型的 `{source, target}`——代码注释自承"撑不住类型化图谱"，但 95% 的图谱可视化场景不需要类型化。
3. **类型化边需要反向边命名规则**：`A sub_of B` → B 的反向边叫什么？`has_sub`？`super_of`？`contains`？反向边是 query 时计算（`link_type_inverses` 配置表）还是写入时物化（双向 INSERT）？这是一连串的复杂度上升。
4. **真实使用中无类型 wikilink 已足够**：`[[xxx]]` 抽取的双向链接 + 物化目录树 + chunk 溯源，组合起来已能覆盖图谱可视化、孤儿页检测、死链清理、原文回看这四大场景。

## Decision

采纳参考项目的三套边并存模型，**永久放弃类型化边**。

### 链接图边（无类型、无权、有向）

```sql
-- 不需要单独的 page_links 表，直接在 pages 表上存数组
ALTER TABLE pages ADD COLUMN in_links  TEXT[] DEFAULT '{}';
ALTER TABLE pages ADD COLUMN out_links TEXT[] DEFAULT '{}';
```

抽取规则：扫 markdown 正文里的 `[[slug-or-title]]` wikilink，A 写 `[[B]]` → `A.out_links += B` 且 `B.in_links += A`（双向冗余存储，反向查询不用扫全表）。

图谱可视化对外暴露：

```typescript
type WikiGraphEdge = { source: string; target: string };  // 有向，slug 标识
// 没有 link_type 字段——永久放弃
```

查询模式：
- `overview` —— top-N 连接数最多的页面（默认）
- `ego` —— 以某 slug 为中心做 BFS 邻域（computeGraphSubset / bfsEgoSlugs）

### 目录树边（两套父子结构并存）

| 字段 | 含义 | 角色 |
|------|------|------|
| `folder_id` | 引用 `wiki_folders.id`（NULL/空 = 根） | source of truth，决定页面在目录树里的位置 |
| `parent_slug` | 引用另一个 page 的 slug | 语义父级，可选 |
| `category_path` | `["AI", "LLM 应用", "RAG"]` | `folder_id` 链路的物化路径缓存 |
| `depth` | `len(category_path)` | 缓存，方便过滤 |
| `wiki_path` | 拼接 `page_type/category_path/title` | 排序用归一化路径 |

`wiki_folders` 表本身是邻接表（`parent_id`）+ 物化路径（`path`）：

```sql
CREATE TABLE wiki_folders (
  id         SERIAL PRIMARY KEY,
  kb_id      INT REFERENCES knowledge_bases(id) ON DELETE CASCADE,
  parent_id  INT REFERENCES wiki_folders(id) ON DELETE CASCADE,  -- 邻接表
  path       TEXT NOT NULL,  -- 物化路径（"/"-joined），方便 LIKE 'prefix%' 查询
  name       TEXT NOT NULL,
  UNIQUE(kb_id, path)
);
```

关键设计：`folder_id` 是 source of truth，`category_path`/`wiki_path`/`depth` 全是从 folder 链路反向重算的缓存（每次写 page 都重算），这样列表/索引/搜索查询不用 join `wiki_folders` 表。深度硬上限 3 层（`WikiCategoryMaxDepth = 3`）。

### 溯源边（页面 → 原文档/chunk）

| 字段 | 格式 | 用途 |
|------|------|------|
| `source_refs` | `["<kb_id>\|<doc_title>", ...]` | 文档级溯源 |
| `chunk_refs` | `["<chunk_uuid>", ...]` | chunk 级精确溯源 |

`summary` 页通常 `chunk_refs` 为空（它是文档级摘要）；`entity`/`concept`/`synthesis`/`comparison` 页带 chunk 级引用。

用途：原文档删除时清掉对应引用、对话里点"查看证据"跳回原文。

### 页面类型（7 种）

| 类型 | 自动/手建 | 含义 |
|------|----------|------|
| `summary` | 自动（ingest） | 文档摘要页——每篇原文档对应一篇 |
| `entity` | 自动（ingest） | 实体页——人/组织/地点等具象对象 |
| `concept` | 自动（ingest） | 概念页——主题/技术/方法论 |
| `index` | 自动（系统） | wiki 索引页（slug 固定 `index`，缺失时自动建默认页） |
| `log` | 自动（系统） | 操作日志页（slug 固定 `log`） |
| `synthesis` | Agent 手建 | 综合分析页——跨文档趋势、洞察 |
| `comparison` | Agent 手建 | 对比页——实体/概念/方案对比 |

`index` / `log` 是系统页，被 `wikiIndexContentPageTypes` 排除在用户目录之外。

### 其他约束

- **slug 唯一性**：同一个 KB 内 slug 唯一（`UNIQUE(kb_id, slug)`），**跨 KB 不唯一**。两个 KB 都有"苹果"实体不冲突。
- **类型字符串清洗**：目录路径里把 `entity/实体/concept/概念/summary/摘要/wiki/页面` 这类标签词过滤掉（`isWikiTypeCategoryLabel`）。
- **类型可多选过滤**：API 接受 `page_types=entity,concept` 这种逗号分隔参数。

## Considered Options

- **8 种语义边（PRD v4.2 原案）**：rejected。LLM 抽取不可靠（70%+ 兜底到 `related_to`）；用户已明确选择"完全照搬参考项目"。
- **预留 nullable `link_type` 字段**：rejected。YAGNI——未来真要做类型化边再 `ALTER TABLE` + 回填即可，schema 一开始复杂化不值得；用户拒绝。
- **类型化边 + 反向边配置表（`link_type_inverses`）**：rejected。复杂度过高（双向 INSERT + 反向命名规则 + LLM 抽取精度），且参考项目实践证明 95% 场景不需要。
- **三套边并存，但用单独的 `page_links` 表替代 in_links/out_links 数组**：rejected for default。数组冗余的查询性能更好（不需要 JOIN），Postgres 的 GIN 索引支持 `@>` 包含查询已足够。`page_links` 表留作未来跨 KB 图谱扩展时再启用。

## Consequences

- **失去的能力**：语义关系查询（"找所有 `sub_of` 关系"不可行）；图谱可视化只能展示"谁连谁"不能展示"什么关系"。
- **获得的能力**：schema 极简（数组 + 物化路径）；抽取可靠（正则搞定，无 LLM 不确定性）；双向查询高效（数组冗余）；目录树高效（物化路径不用递归 CTE）。
- **物化路径缓存的代价**：每次写 page（含 folder_id 变更）都要重算 `category_path`/`depth`/`wiki_path`，应用层 service 必须兜住——建议在 `PageRepository.save()` 里做透明重算，不让上层调用方操心。
- **深度硬上限 3 层**：超出会被拒绝（API 返回 400）。这是有意的——防止用户搭 10 层深目录导致 UI 难以浏览。
- **系统页保护**：`index`/`log` 两个 slug 在每个 KB 内保留，用户不能创建 slug 为 `index` 或 `log` 的页面（API 校验拒绝）。
- **跨 KB slug 不唯一**：跨 KB 检索同名实体的处理留给应用层（合并 vs 分别展示），不在 schema 层强制。
- **未来扩展路径**：如果真要做类型化边，新增 `page_links(source_id, target_id, link_type, weight)` 表 + 触发器从 `out_links` 数组同步——历史数据 link_type 留空即可，不需要回填。

## 参考实现

参考项目（Go）已实现此模式：

- `internal/types/wiki_page.go:22` — `wikiLinkRegex = regexp.MustCompile(\`\[\[([^\]]+)\]\]\`)` 抽取规则
- `internal/types/wiki_page.go:111-131` — `WikiPageType*` 常量定义（7 种页面类型）
- `internal/types/wiki_page.go:277` — `wikiIndexContentPageTypes`（系统页过滤）
- `internal/types/wiki_page.go:469-500` — `WikiGraphData` / `WikiGraphNode` / `WikiGraphEdge` 对外暴露结构
- `internal/types/wiki_page.go:91` — `isWikiTypeCategoryLabel` 目录路径清洗
- `internal/types/wiki_page.go:71` — `SplitWikiPageTypes` 多选过滤
- `internal/types/wiki_page.go:264` — `GetIndex` 缺失时自动建默认 index 页
- `internal/application/repository/wiki_folder.go` — 邻接表 + 物化路径实现

llm_wiki3.0 用 FastAPI + SQLAlchemy：
- 表结构可直接照搬（`pages.in_links/out_links/source_refs/chunk_refs` 用 `ARRAY(Text)` 或 `JSONB`；`wiki_folders` 邻接表 + `path` 物化路径列）。
- wikilink 抽取用 Python `re.findall(r'\[\[([^\]]+)\]\]', body)` 实现。
- 物化路径重算放在 `PageService.save()` 里做透明兜底（SQLAlchemy 的 `@before_save` event hook）。
- 图谱查询用 SQLAlchemy 的 `func.array_contains` 或原生 SQL 的 `@>` 操作符走 GIN 索引。
