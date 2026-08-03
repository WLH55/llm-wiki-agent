# Spec：models 字段注释补齐

- 创建时间：2026-08-03_17-38
- 通道：FAST（机械性注释补充，无行为变更）
- Goal：为 `backend/app/models/` 下全部 ORM 表模型的每个字段添加中文注释
- In Scope：12 个 model 文件（base / chunk / document / kb / kb_wiki_config / rag_config / reserved / search_log / source / task_runtime / user / wiki）
- Out of Scope：不修改字段定义、类型、约束、默认值与表结构；不修改 `__init__.py` / `database.py`；不改迁移脚本

## Research Findings

- 字段语义的权威来源是 `backend/alembic/versions/001_initial.py` 中的 `COMMENT ON COLUMN`（文案取自 2026-07-27 数据库表逐表审批记录 spec），注释口径与其保持一致。
- 所有模型文件均为 UTF-8（无 BOM），保持原编码写入。

## Plan / Checklist

- [x] base.py：TimestampMixin（created_at / updated_at / deleted_at）、TenantMixin（tenant_id）加注释
- [x] chunk.py / document.py / kb.py / kb_wiki_config.py / rag_config.py 全字段加注释
- [x] reserved.py / search_log.py / source.py / task_runtime.py / user.py / wiki.py 全字段加注释
- [x] 验证：`python -m py_compile` 通过；脚本检查所有 `Mapped` 字段上一行均有 `#` 注释（0 缺失）

## Execute Log

- 变更文件：12 个 model 文件，合计 +256 行（仅新增注释行）
- Mixin 字段（创建/更新时间、软删除时间、tenant_id）在 `base.py` 一次性注释，供继承表共用

## Review Verdict

- Axis-1 目标/范围：PASS（注释覆盖全部表字段，范围明确）
- Axis-2 Spec-代码一致性：PASS（未改动任何字段定义，仅新增注释）
- Axis-3 代码质量：PASS（语法编译通过，无行为风险）
- Overall Verdict：PASS

## Plan-Execution Diff

- 无偏差。
