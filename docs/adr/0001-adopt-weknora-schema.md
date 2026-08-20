# ADR-0001: 数据库层全量采用 WeKnora 表结构

- 状态：已接受（Accepted）
- 日期：2026-08-20
- 决策人：项目所有者（用户）
- 关联 Spec：`mydocs/specs/2026-08-20_16-24_知识库表结构重设计.md`

## 背景

本项目原有 23 张表的自研 schema（BIGINT 主键 + public_id 双轨、全库无外键、sources→documents→document_revisions 三层文档模型、向量内嵌 content_chunks、Dramatiq+Redis 任务队列）。经与 WeKnora 53 张表结构逐域对照（见 `mydocs/database-tables-catalog.md` 与 Spec §2），双方各有所长：本项目在文档版本化、Wiki 血缘实体化、任务两级账本上更强；WeKnora 在标签、块编辑、资源层、多渠道接入等领域能力覆盖上更全。

## 决策

**推倒现有 23 张表，53 张表全量逐字段照搬 WeKnora 结构（含 chat/IM/org/Agent/MCP 等暂未使用的域，先建后用），后续按本项目需求渐进修改（边做边改）。**

本地化仅限必要项：UUID 默认值用 PG16 内建 `gen_random_uuid()`；向量 HNSW 与 BM25 索引参数沿用本项目在 ParadeDB 上已验证的配置（halfvec cosine、chinese_lindera）；列注释中文化。

## 备选方案

| 方案 | 结论 |
|---|---|
| A. 保留自有架构，仅补 WeKnora 缺失的领域能力 | 改造可控、不破坏已验证链路，但需逐域设计决策（用户在 grilling 中评估后放弃，认为过程过重） |
| **B. 全量照搬 WeKnora 结构（选定）** | 零设计成本、直接获得成熟领域模型全貌；代价见下 |
| C. 混合（部分域对齐） | 留下两套风格并存的维护负担 |

## 理由

1. 用户明确偏好「先拿到完整成熟结构、再按需小步修改」的演进路径，胜过「先精确设计再实现」。
2. WeKnora 结构经生产验证，且同为 ParadeDB（PostgreSQL 内核）部署，DDL 可直接适用。
3. 本项目处于开发期，无存量数据迁移负担，推倒成本处于最低点。

## 后果

**获得**：完整的知识库/会话/Agent/渠道/协作领域模型；标签、块编辑与修订、资源注册、死信归档等能力位；与 WeKnora 生态对照时的概念一致性。

**损失（需要时边做边补回）**：
- 文档不可变修订（documents/document_revisions 三层）→ WeKnora 单条目模型无版本概念
- Wiki 证据级血缘（links/document_refs/evidence_refs 三张实体表）→ 降为页面上的 JSON 字段
- search_logs 检索审计与反馈
- processing_runs/spans 两级任务账本（含 Reaper/Dramatiq 契约）→ 替换为单层跨度树 + DB 队列表
- BYOK（user_llm_keys 用户自带密钥）

**约束**：业务代码（services/repos/workers/API/tests）在 schema 替换后需逐域重写，知识库域优先；Dramatiq 与 task_pending_ops 的取舍是独立后续决策。

## 回滚

git revert 对应提交并重建数据库（alembic 新链从零开始，无增量耦合）。
