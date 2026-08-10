# 多源挂载（统一 Source 抽象 + 无优先级）

> 状态：Source Adapter 与无优先级决策保留；`sources` 表字段和生命周期已由 [ADR-0012](0012-approved-rag-wiki-database-boundaries.md) 取代，不再保存 `sync_status`，运行状态归属 `processing_runs`。

llm_wiki3.0 的多源挂载采用 **统一 `sources` 表 + adapter 模式**：

- 一个 KB 可同时挂 N 个 source（manual / RSS / Yuque / Feishu / Notion 等），所有 source 的 chunks 共享同一 `kb_id`。
- `sources` 表统一存所有类型：`source_type` + `config JSONB` + `sync_cursor JSONB` + `sync_status`。
- 每种 source_type 对应一个 `SourceAdapter` 实现（拉取 / 解析 / 增量游标推进）。
- **所有 source 平等**——检索按内容相关性排序，**不做 source boost 加权**，**不做更新覆盖优先级**。同 URL 文档更新时旧 chunks 软删除 + 重嵌入；跨 source 同标题不冲突（`doc_id` 全局唯一）。

## Decision

### Phase 划分（明确 P1 / P4 / P5 / P6 各做什么）

| Phase | Source 类型 | 状态 |
|-------|------------|------|
| **P1** | `sources` 表 schema + `SourceAdapter` 抽象接口 + **manual（手动上传）adapter** | schema ready + 一个可用 adapter |
| **P4** | RSS adapter + 本地目录监控 adapter | pull 模式 |
| **P5** | Yuque（语雀）adapter | API + 增量同步 |
| **P6** | Feishu（飞书文档）adapter + Notion adapter | API + 增量同步 |

P1 只做 manual + schema，后续 phase 加 adapter 不需要改 schema。

### sources 表 schema

```sql
CREATE TABLE sources (
  id              SERIAL PRIMARY KEY,
  kb_id           INT REFERENCES knowledge_bases(id) ON DELETE CASCADE,
  source_type     TEXT NOT NULL,         -- manual / rss / yuque / feishu / notion / local_dir
  name            TEXT NOT NULL,         -- 用户起的别名（如"研发组语雀"）
  config          JSONB NOT NULL,        -- 类型相关配置（见下）
  sync_cursor     JSONB,                 -- 增量游标（类型相关，见下）
  sync_status     TEXT NOT NULL DEFAULT 'idle',  -- idle / syncing / error / disabled
  last_synced_at  TIMESTAMPTZ,
  created_by      INT REFERENCES users(id),
  created_at      TIMESTAMPTZ DEFAULT now(),
  UNIQUE(kb_id, source_type, name)
);
```

### 各 source_type 的 config + sync_cursor

| source_type | config | sync_cursor | adapter 模式 |
|-------------|--------|-------------|-------------|
| `manual` | `{}`（无配置） | `{}`（每次上传即增量，无游标） | push（用户主动上传） |
| `rss` | `{"feed_url": "https://...", "poll_interval_min": 30}` | `{"last_build_date": "2026-07-08T...", "etag": "..."}` | pull（定时拉取） |
| `local_dir` | `{"path": "/data/docs", "watch": true}` | `{"last_scanned_at": "...", "file_mtimes": {...}}` | pull（文件系统扫描） |
| `yuque` | `{"token": "...", "namespace": "my-org", "book_id": 123}` | `{"last_doc_updated_at": "..."}` | API + 增量同步 |
| `feishu` | `{"app_id": "...", "app_secret": "...", "wiki_space_id": "..."}` | `{"last_doc_updated_at": "..."}` | API + 增量同步 |
| `notion` | `{"integration_token": "...", "database_id": "..."}` | `{"last_edited_time": "..."}` | API + 增量同步 |

### SourceAdapter 抽象接口

```python
class SourceAdapter(Protocol):
    source_type: str

    def validate_config(self, config: dict) -> None: ...

    def fetch_incremental(
        self, config: dict, cursor: dict | None
    ) -> tuple[list[RawDocument], dict]:
        """
        返回 (本次拉到的原始文档列表, 推进后的新游标)。
        cursor=None 表示首次全量拉取。
        """
        ...

    def normalize(self, raw: RawDocument) -> NormalizedDocument:
        """把各 source 的原始格式统一成 NormalizedDocument（title + body_md + source_url + extra）。"""
        ...
```

### 冲突处理

- **同 source 内文档更新**：adapter 通过 `doc_natural_key`（如 RSS 的 link / Yuque 的 doc_id）判断是更新还是新增；更新时把旧 chunks 标记 `deleted_at`（软删除），新 chunks 重嵌入；wiki_pages 的 `source_refs` 自动跟随更新。
- **跨 source 同标题**：不冲突——`doc_id` 是全局 UUID（不依赖标题）；检索时按内容相关性排序，不按 source 类型加权。
- **删除 source**：`DELETE /api/sources/{id}` → 软删除（`sources.deleted_at`）+ 该 source 所有 chunks 软删除（`content_chunks.deleted_at`）+ wiki_pages 的对应 `source_refs` 清理；KB 总 chunks 数减少；后续检索不返回。

### RBAC

- source 继承 KB 的权限：能读 KB 的用户能读所有 source 的 chunks；能写 KB 的用户能管理 source（添加 / 删除 / 修改 sync 配置）。
- 创建 source 权限：KB owner + admin + contributor（editor 在 ADR-0002 语义下也可）。
- API Key / OAuth token 类配置：与 BYOK 同等加密存储（Fernet），密钥派生自 env var。

## Considered Options

- **B. A + 检索 boost 优先级（`sources.boost_factor`）**：rejected。YAGNI——所有 source 平等已能覆盖绝大多数场景；boost 引入用户配置复杂度 + 检索排序多一个变量。如果未来真有需求再加（schema 改动小）。
- **C. A + 更新覆盖优先级（manual > Yuque > Feishu > RSS）**：rejected。同标题文档高优先级覆盖低优先级 = 用户可能丢数据；语义复杂；不必要。
- **每 source 单独的表（manual_sources / rss_sources / ...）**：rejected。N 个表 N 套 schema；新增 source_type 要 migration；adapter 模式更优雅。
- **source 级 RBAC（不同 source 给不同权限）**：rejected。粒度过细，运维噩梦；KB 级权限已够。

## Consequences

- **schema 新增表**：`sources`（上面已列）。
- **adapter 注册机制**：Python `SourceAdapter` 实现通过 entry point 或工厂注册；新增 source_type 不需要改核心代码（只需新加 adapter 模块）。
- **异步任务**：RSS / Yuque / Feishu 等 pull/api 模式走 Redis 队列 + Python worker（参 [CONTEXT.md Redis + 任务队列]）；manual 是同步上传 + 异步解析。
- **运营成本**：用户配置 pull/api 类 source 时需要填 token / OAuth（与 BYOK 类似的引导流程）。
- **失去的能力**：无法表达"manual 比 RSS 更权威"这类业务约束（如果未来真需要，靠 `boost_factor` 字段扩展）。

## Open Questions（留给未来 grilling）

- **Open Question A（source 失败的降级）**：某个 source API 故障（如飞书服务宕机）时，KB 其他 source 的检索不应受影响——这已经天然满足（chunks 已在 DB）。但 source 同步任务失败时是否告警？候选：① 静默重试（默认 3 次）；② source.sync_status='error' + 用户 UI 看到红色标记；③ IM 通知（P5 加）。推荐 ②。
- **Open Question B（source 级 LLM 配置）**：不同 source 用不同嵌入模型？（如 manual 用 bge-m3，RSS 用更轻的模型）。当前 v4.2 不做——KB 级绑定统一模型（ADR-0001）；如果未来需要，schema 改动小。

## 参考实现

- Python adapter 模式：`SourceAdapter` Protocol + 工厂注册（`SOURCE_ADAPTERS: dict[str, SourceAdapter]`）
- RSS 解析：`feedparser` 库
- Yuque API：`https://www.yuque.com/api/v2/`
- Feishu API：`https://open.feishu.cn/open-apis/`
- Notion API：`https://api.notion.com/v1/`
- 本地目录监控：`watchdog` 库（实时）+ 定时全扫（兜底）
