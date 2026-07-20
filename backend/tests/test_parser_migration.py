"""parser hardening Alembic 迁移结构测试。"""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy.dialects.postgresql import JSONB


class _FakeOp:
    def __init__(self):
        self.added = []
        self.dropped = []

    def add_column(self, table_name, column):
        self.added.append((table_name, column))

    def drop_column(self, table_name, column_name):
        self.dropped.append((table_name, column_name))


def _load_migration(monkeypatch, fake_op):
    monkeypatch.setitem(sys.modules, "alembic", SimpleNamespace(op=fake_op))
    migration_path = Path(__file__).parents[1] / "alembic" / "versions" / "002_parser_hardening.py"
    spec = importlib.util.spec_from_file_location("parser_hardening_002", migration_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parser_migration_upgrade_and_downgrade(monkeypatch):
    fake_op = _FakeOp()
    migration = _load_migration(monkeypatch, fake_op)
    migration.upgrade()
    assert [table for table, _ in fake_op.added] == ["documents"] * 3
    columns = {column.name: column for _, column in fake_op.added}
    assert set(columns) == {"parser_engine", "parse_error_code", "parse_metadata"}
    assert columns["parser_engine"].nullable is False
    assert str(columns["parser_engine"].server_default.arg) == "builtin"
    assert columns["parse_error_code"].nullable is True
    assert isinstance(columns["parse_metadata"].type, JSONB)
    assert columns["parse_metadata"].nullable is False
    assert str(columns["parse_metadata"].server_default.arg) == "'{}'::jsonb"
    migration.downgrade()
    assert fake_op.dropped == [
        ("documents", "parse_metadata"),
        ("documents", "parse_error_code"),
        ("documents", "parser_engine"),
    ]
