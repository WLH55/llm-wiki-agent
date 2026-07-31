"""Revision 化 RAG 数据迁移的关键 DDL 契约。"""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace


class _FakeOp:
    def __init__(self):
        self.statements: list[str] = []

    def execute(self, statement: str) -> None:
        self.statements.append(statement)


def _load_migration(monkeypatch, fake_op):
    monkeypatch.setitem(sys.modules, "alembic", SimpleNamespace(op=fake_op))
    path = Path(__file__).parents[1] / "alembic" / "versions" / "004_rag_revisions.py"
    assert path.exists(), "004_rag_revisions.py must exist"
    spec = importlib.util.spec_from_file_location("rag_revisions_004", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revision_migration_builds_candidate_and_activation_contract(monkeypatch):
    fake_op = _FakeOp()
    migration = _load_migration(monkeypatch, fake_op)
    assert migration.down_revision == "003"
    migration.upgrade()
    sql = "\n".join(fake_op.statements).lower()
    assert "create table document_revisions" in sql
    assert "create table kb_rag_configs" in sql
    assert "active_revision_id" in sql
    assert "processing_run_id" in sql
    assert "embedding_run_id" in sql
    assert "alter column embedding drop not null" in sql
    assert "unique (revision_id, chunk_index)" in sql
    assert "ck_content_chunks_embedding_shape" in sql


def test_revision_migration_has_explicit_downgrade(monkeypatch):
    fake_op = _FakeOp()
    migration = _load_migration(monkeypatch, fake_op)
    migration.downgrade()
    sql = "\n".join(fake_op.statements).lower()
    assert "drop table if exists document_revisions" in sql
    assert "drop table if exists kb_rag_configs" in sql
    assert "alter column embedding set not null" in sql
