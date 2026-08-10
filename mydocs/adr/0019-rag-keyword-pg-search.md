# ADR: RAG 关键词检索采用 pg_search（ParadeDB）

> **Status**: Accepted（2026-08-06，grilling 确认）
> **Supersedes**: `ILIKE` 假 BM25（demo 现状）；`tsvector + zhparser` 方案（PRD v4.2 明确否决）
> **关联 Spec**: `mydocs/specs/2026-08-06_17-43_RAG知识库检索设计.md`

## 背景

检索侧 demo 的 `bm25_search` 实为 `ILIKE '%q%'` + 恒定 rank，无排序无中文分词，不构成关键词检索。PRD v4.2 已决策"BM25 用 PostgreSQL `pg_search` 扩展，禁止用 tsvector + ts_rank 冒充"；`001_initial` migration 已预留"BM25 镜像就绪后另开任务"。WeKnora 生产环境同款方案（`content ||| ?` + `paradedb.score(id)` + `chinese_lindera` 分词器），已验证。

## 决策

关键词检索采用 **ParadeDB `pg_search`**：

- postgres 镜像升级为 `paradedb/paradedb`（自带 pg_search + pgvector）。
- `content_chunks` 建 `USING bm25` 索引（`key_field=id`，`chinese_lindera` 中文分词器）。
- 查询改 `text ||| :q` + `paradedb.score(id)` 排序，阈值默认 0.3（score 归一化到 0–1）。
- 清理废弃 `zhparser` / `chinese_zh`（001 migration 已移除，`postgres/init-extensions.sql` 残留同步清理）。

## 原因

- 真 BM25 排名质量优于 `ts_rank_cd`，中文分词（Lindera）优于字典式 zhparser。
- 与既有设计决策一致，WeKnora 同款已验证，无需自研。

## 后果

- **AGPL-3.0 许可**：自部署内网服务无影响；若未来对外分发需评估商业版。
- **部署变更**：postgres 镜像切换影响 compose 环境；已有数据卷不受影响（扩展在 PG 安装目录，`CREATE EXTENSION` 由 alembic 幂等承担）。
- **索引维护**：BM25 索引随 `content_chunks` 写入自动更新；当前无存量数据。
- 向量检索路径（halfvec + partial HNSW）不受影响。
