"""Unit tests for PsycopgExecutor with a faked psycopg.connect (no I/O, no socket).

The fake connection records every setting the executor must apply
(statement_timeout option, read_only vs autocommit, prepare_threshold,
extended-protocol execute, ROLLBACK-when-closed, close-on-every-path).
"""

import psycopg
import pytest

from postgres_mcp.domain.config import load_config
from postgres_mcp.infrastructure.adapters.postgres import (
    ROW_CAP,
    TIMEOUT_MS,
    PsycopgExecutor,
)


def _config(**overrides):
    env = {"PG_USER": "u", "PG_PASSWORD": "p", **overrides}
    return load_config(env)


class FakeCursor:
    def __init__(self, description=None, rows=(), rowcount=0, error=None):
        self.description = description
        self._rows = list(rows)
        self.rowcount = rowcount
        self._error = error
        self.executed = []
        self.fetch_size = None

    def execute(self, sql, prepare=False):
        self.executed.append({"sql": sql, "prepare": prepare})
        if self._error is not None:
            raise self._error
        return None

    def fetchmany(self, size):
        self.fetch_size = size
        return self._rows[:size]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeConn:
    def __init__(self, cursor, rollback_error=None):
        self._cursor = cursor
        self._rollback_error = rollback_error
        self.read_only = False
        self.autocommit = False
        self.prepare_threshold = None
        self.rolled_back = False
        self.closed = False

    def cursor(self):
        return self._cursor

    def rollback(self):
        self.rolled_back = True
        if self._rollback_error is not None:
            raise self._rollback_error

    def close(self):
        self.closed = True


def _install_fake_connect(monkeypatch, cursor, seen, rollback_error=None):
    holder = {}

    def fake_connect(**kwargs):
        seen.update(kwargs)
        holder["conn"] = FakeConn(cursor, rollback_error=rollback_error)
        return holder["conn"]

    monkeypatch.setattr(psycopg, "connect", fake_connect)
    return holder


def _pg_error(message, sqlstate):
    err = psycopg.OperationalError(message)
    err.sqlstate = sqlstate
    return err


def test_closed_select_uses_read_only_and_prepared_protocol(monkeypatch):
    cursor = FakeCursor(description=(("?column?",),), rows=[(1,)])
    seen = {}
    holder = _install_fake_connect(monkeypatch, cursor, seen)
    result = PsycopgExecutor(_config()).execute("SELECT 1", True)
    conn = holder["conn"]
    assert seen == {
        "host": "127.0.0.1",
        "port": 5423,
        "dbname": "postgres",
        "user": "u",
        "password": "p",
        "options": f"-c statement_timeout={TIMEOUT_MS}",
    }
    assert TIMEOUT_MS == 15000
    assert conn.read_only is True
    assert conn.autocommit is False
    assert conn.prepare_threshold == 0
    assert cursor.executed == [{"sql": "SELECT 1", "prepare": True}]
    assert cursor.fetch_size == ROW_CAP + 1
    assert result.columns == ("?column?",)
    assert result.rows == ((1,),)
    assert result.truncated is False
    assert result.row_count == 1
    assert conn.rolled_back is True
    assert conn.closed is True


def test_closed_select_at_exact_cap_is_not_truncated(monkeypatch):
    rows = [(i,) for i in range(ROW_CAP)]
    cursor = FakeCursor(description=(("n",),), rows=rows)
    holder = _install_fake_connect(monkeypatch, cursor, {})
    result = PsycopgExecutor(_config()).execute("SELECT n FROM t", True)
    assert result.rows == tuple(rows)
    assert result.truncated is False
    assert result.row_count == ROW_CAP
    assert holder["conn"].closed is True


def test_closed_over_cap_select_truncates_with_flag(monkeypatch):
    rows = [(i,) for i in range(ROW_CAP + 1)]
    cursor = FakeCursor(description=(("n",),), rows=rows)
    holder = _install_fake_connect(monkeypatch, cursor, {})
    result = PsycopgExecutor(_config()).execute("SELECT n FROM t", True)
    assert len(result.rows) == ROW_CAP
    assert result.rows == tuple(rows[:ROW_CAP])
    assert result.truncated is True
    assert result.row_count == ROW_CAP
    assert holder["conn"].rolled_back is True
    assert holder["conn"].closed is True


def test_open_write_uses_autocommit_and_reports_rowcount(monkeypatch):
    cursor = FakeCursor(description=None, rowcount=1)
    holder = _install_fake_connect(monkeypatch, cursor, {})
    result = PsycopgExecutor(_config(PG_ALLOW_WRITES="1")).execute(
        "INSERT INTO t VALUES (1)", False
    )
    conn = holder["conn"]
    assert conn.read_only is False
    assert conn.autocommit is True
    assert result.columns == ()
    assert result.rows == ()
    assert result.truncated is False
    assert result.row_count == 1
    assert conn.rolled_back is False
    assert conn.closed is True


def test_open_ddl_with_unknown_rowcount_reports_zero(monkeypatch):
    cursor = FakeCursor(description=None, rowcount=-1)
    holder = _install_fake_connect(monkeypatch, cursor, {})
    result = PsycopgExecutor(_config(PG_ALLOW_WRITES="1")).execute(
        "CREATE TABLE x(a int)", False
    )
    assert result.row_count == 0
    assert holder["conn"].closed is True


def test_pg_error_propagates_after_rollback_and_close(monkeypatch):
    error = _pg_error("permission denied for table cuenta_p07", "42501")
    cursor = FakeCursor(description=(("n",),), error=error)
    holder = _install_fake_connect(monkeypatch, cursor, {})
    with pytest.raises(psycopg.OperationalError) as excinfo:
        PsycopgExecutor(_config()).execute("INSERT INTO cuenta_p07 VALUES (1)", True)
    assert excinfo.value is error
    conn = holder["conn"]
    assert conn.rolled_back is True
    assert conn.closed is True


def test_failing_rollback_does_not_mask_the_original_error(monkeypatch):
    error = _pg_error("connection failed: host unreachable", "08001")
    cursor = FakeCursor(description=(("n",),), error=error)
    holder = _install_fake_connect(
        monkeypatch, cursor, {}, rollback_error=RuntimeError("rollback also failed")
    )
    with pytest.raises(psycopg.OperationalError) as excinfo:
        PsycopgExecutor(_config()).execute("SELECT 1", True)
    assert excinfo.value is error
    assert holder["conn"].closed is True
