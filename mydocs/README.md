# mydocs 文档规范

项目唯一持久化知识库。按 **SDD-RIPER 协议**（`sdd-riper-one` skill）+ **domain-modeling**（`grill-with-docs` skill）管理。

## 目录职责

| 目录/文件 | 放什么 | 规范 |
|---|---|---|
| `specs/` | SDD Spec | 命名 `YYYY-MM-DD_hh-mm_<Task>.md`；必须带 RIPER 状态头；Spec is Truth |
| `context/CONTEXT.md` | 唯一术语表 | 纯术语 + Avoid 反例；不混实现细节 |
| `context/docs/adr/` | 架构决策记录（编号序列） | `NNNN-slug.md`；难逆转 / 无上下文会惊讶 / 真实权衡 三条件才写 |
| `context/` | context bundle 快照 | `YYYY-MM-DD_hh-mm_<task>_context_bundle.md` |
| `glossary/` | 术语附录（历史） | 内容最终应并入 CONTEXT.md |
| 根级 `*.md` | 架构 / 设计 / 研究文档 | 见下"根级文档" |

> 说明：`archive/`、`codemap/` 暂不启用（2026-08-06 用户决策）。

## 硬规则（sdd-riper-one）

1. **No Spec, No Code**：未落盘 spec 不进实现。
2. **Plan Approved 门禁**：未收到精确字样 `Plan Approved` 不进入 Execute。
3. **Spec is Truth**：聊天决议必须回源 spec；spec 是唯一真相源。
4. **Reverse Sync**：实现偏差必须回写 spec（`Plan-Execution Diff`）。
5. `specs/` 只放 spec 文档；HTML、外部调研材料不得混入。

## 硬规则（domain-modeling / grill-with-docs）

1. `CONTEXT.md` 是唯一术语表，任何时候保持纯净（无实现细节）。
2. 术语冲突 → 立即修改 CONTEXT.md，不批量攒。
3. 新决策满足三条件（难逆转 / 无上下文会惊讶 / 真实权衡）→ 写 ADR，编号 = 扫描 `context/docs/adr/` 最大值 + 1。
4. ADR 记录"做了啥 + 为什么"，不是填充模板。

## 根级文档（当前未归类，2026-08-06 状态）

- `prd-v4.2.md` — 产品需求文档（路线图）
- `kb-architecture.md` / `rag-architecture.md` / `wiki-architecture.md` / `multi-tenant-architecture.md` / `parser-design-pattern.md` — 架构设计文档
- `task-queue-design.md` — 任务队列设计（**当前实现为准**，2026-08-06 起）
- `dramatiq-migration-decision.md` — 迁移决策调研快照（真相以 ADR 2026-08-05 为准）
- `taskiq-outbox-mechanism.md` — 已废弃实现详解（被 ADR-0018 记录、后被 Dramatiq 迁移取代）
- `task-queue-comparison-weknora-vs-llm-wiki-agent.md` — WeKnora 对比调研
- `GBrain知识库设计剖析.md` / `任务运行时三表设计与消息队列原理详解.md` / `ts-nextjs-guide-for-python-java-vue-developer.md` — 研究 / 教程
- `llm-wiki-design-decision.html` / `obsidian-wiki-research.html` / `obsidian-wiki-vs-gbrain-comparison.html` — 历史调研 HTML（2026-08-06 从 specs/ 移出）
- `LLM-Wiki-Parser-Production-Hardening-Guide.docx` — 指南（二进制，不入索引）

## ADR 位置说明

- 规范位置：`context/docs/adr/`（`0001`–`0019` 连续编号）。
- 历史位置：`mydocs/adr/2026-08-05_dramatiq-migration.md`（Dramatiq 迁移 ADR，未入编号序列）。若未来并入编号序列，建议占 `0019`，`0019-rag-keyword-pg-search` 顺延为 `0020`。
