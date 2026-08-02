"""初始迁移 001 一次性建表的关键 DDL 契约。

旧增量迁移 002-005 已删除，相关表/列已并入重建后的 001_initial.py。
本测试断言 001 在一次 upgrade 中创建全部目标表、关键约束与注释。
"""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace


class _FakeOp:
    """记录所有 op.execute 语句，便于对 DDL 文本做契约断言。"""

    def __init__(self):
        self.statements: list[str] = []

    def execute(self, statement: str) -> None:
        self.statements.append(statement)


def _load_migration(monkeypatch, fake_op):
    monkeypatch.setitem(sys.modules, "alembic", SimpleNamespace(op=fake_op))
    path = Path(__file__).parents[1] / "alembic" / "versions" / "001_initial.py"
    assert path.exists(), "001_initial.py must exist"
    spec = importlib.util.spec_from_file_location("initial_001", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_initial_migration_is_base_revision(monkeypatch):
    """001 必须是迁移链起点，不依赖任何前置迁移。"""
    fake_op = _FakeOp()
    migration = _load_migration(monkeypatch, fake_op)
    assert migration.down_revision is None
    assert migration.revision == "001"


def test_initial_migration_creates_all_target_tables(monkeypatch):
    """001 一次性创建全部 23 张目标表（去 FK、按 spec 定稿）。"""
    fake_op = _FakeOp()
    migration = _load_migration(monkeypatch, fake_op)
    migration.upgrade()
    sql = "\n".join(fake_op.statements).lower()

    # 基础设施（7）
    for table in [
        "tenants",
        "users",
        "organizations",
        "org_members",
        "kb_shares",
        "llm_providers",
        "user_llm_keys",
    ]:
        assert f"create table {table}" in sql, f"缺少建表: {table}"

    # 共享根与配置（4）
    for table in ["knowledge_bases", "kb_rag_configs", "kb_wiki_configs", "sources"]:
        assert f"create table {table}" in sql, f"缺少建表: {table}"

    # 文档链（3）
    for table in ["documents", "document_revisions", "content_chunks"]:
        assert f"create table {table}" in sql, f"缺少建表: {table}"

    # Wiki（5）
    for table in [
        "wiki_folders",
        "wiki_pages",
        "wiki_page_links",
        "wiki_page_document_refs",
        "wiki_page_evidence_refs",
    ]:
        assert f"create table {table}" in sql, f"缺少建表: {table}"

    # 运行支撑（3）
    for table in ["processing_runs", "processing_spans", "task_outbox"]:
        assert f"create table {table}" in sql, f"缺少建表: {table}"

    # 检索日志（1）
    assert "create table search_logs" in sql


def test_initial_migration_drops_legacy_fulltext_infra(monkeypatch):
    """001 不再创建 zhparser / chinese_zh / search_vector / GIN / tsvector trigger。"""
    fake_op = _FakeOp()
    migration = _load_migration(monkeypatch, fake_op)
    migration.upgrade()
    sql = "\n".join(fake_op.statements).lower()
    assert "zhparser" not in sql
    assert "chinese_zh" not in sql
    assert "search_vector" not in sql
    assert "tsvector" not in sql
    assert "create extension if not exists vector" in sql


def test_initial_migration_has_no_foreign_keys(monkeypatch):
    """全库不建外键：001 的 DDL 不得出现 references 关键字。"""
    fake_op = _FakeOp()
    migration = _load_migration(monkeypatch, fake_op)
    migration.upgrade()
    sql = "\n".join(fake_op.statements).lower()
    assert "references" not in sql


def test_initial_migration_carries_key_constraints(monkeypatch):
    """关键约束与索引按 spec 定稿就位。"""
    fake_op = _FakeOp()
    migration = _load_migration(monkeypatch, fake_op)
    migration.upgrade()
    sql = "\n".join(fake_op.statements).lower()

    # content_chunks 两阶段激活契约
    assert "unique (revision_id, chunk_index)" in sql
    assert "ck_content_chunks_embedding_shape" in sql
    assert "embedding           halfvec" in sql
    # HNSW 固定参数（spec 决策#8）：m=16、ef_construction=64、cosine
    assert "using hnsw" in sql
    assert "halfvec_cosine_ops" in sql
    assert "m = 16" in sql
    assert "ef_construction = 64" in sql
    # content_chunks 建表块内不保留旧列 chunk_type / wiki_page_id
    chunks_block = sql.split("create table content_chunks")[1].split("create index")[0]
    assert "chunk_type" not in chunks_block
    assert "wiki_page_id" not in chunks_block

    # processing_runs fencing（ADR-0018）
    assert "execution_token" in sql
    assert "execution_epoch" in sql
    assert "lease_expires_at" in sql
    assert "ck_processing_runs_lease_shape" in sql
    assert "create table task_outbox" in sql

    # documents 不再保留文件级旧列
    assert "minio_key" not in sql
    assert "doc_id" not in sql.split("create table documents")[1].split("create table")[0]

    # manual source 唯一索引
    assert "uq_sources_manual_active_per_kb" in sql


def test_initial_migration_adds_comments(monkeypatch):
    """每张目标表都有中文表注释。"""
    fake_op = _FakeOp()
    migration = _load_migration(monkeypatch, fake_op)
    migration.upgrade()
    sql = "\n".join(fake_op.statements)
    expected_tables = [
        "tenants",
        "users",
        "organizations",
        "org_members",
        "kb_shares",
        "llm_providers",
        "user_llm_keys",
        "knowledge_bases",
        "kb_rag_configs",
        "kb_wiki_configs",
        "sources",
        "documents",
        "document_revisions",
        "content_chunks",
        "wiki_folders",
        "wiki_pages",
        "wiki_page_links",
        "wiki_page_document_refs",
        "wiki_page_evidence_refs",
        "processing_runs",
        "processing_spans",
        "task_outbox",
        "search_logs",
    ]
    for table in expected_tables:
        assert f"COMMENT ON TABLE {table} IS" in sql, f"缺少表注释: {table}"


def test_initial_migration_has_explicit_downgrade(monkeypatch):
    """downgrade 必须反序 DROP 全部表。"""
    fake_op = _FakeOp()
    migration = _load_migration(monkeypatch, fake_op)
    migration.downgrade()
    sql = "\n".join(fake_op.statements).lower()
    for table in [
        "search_logs",
        "task_outbox",
        "processing_spans",
        "processing_runs",
        "wiki_page_evidence_refs",
        "wiki_pages",
        "tenants",
    ]:
        assert f"drop table if exists {table}" in sql, f"downgrade 缺少 DROP: {table}"
