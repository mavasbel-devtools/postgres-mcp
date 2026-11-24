"""Unit tests for handle_execute_sql with stub executors (no I/O)."""

import psycopg
import pytest
from mcp.server.mcpserver.exceptions import ToolError

from postgres_mcp.application.ports import ExecutorPort, QueryResult
from postgres_mcp.domain.config import load_config
from postgres_mcp.infrastructure.adapters.stdio import handle_execute_sql


def _closed_config():
    return load_config({"PG_USER": "u", "PG_PASSWORD": "p"})


def _open_config():
    return load_config({"PG_USER": "u", "PG_PASSWORD": "p", "PG_ALLOW_WRITES": "1"})


class StubExecutor(ExecutorPort):
    def __init__(self, result=None, error=None):
        self._result = result
        self._error = error
        self.calls = []

    def execute(self, sql: str, read_only: bool) -> QueryResult:
        self.calls.append({"sql": sql, "read_only": read_only})
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result


def _pg_error(message, sqlstate):
    err = psycopg.OperationalError(message)
    err.sqlstate = sqlstate
    return err


def test_allowed_select_returns_result_shape_and_read_only():
    stub = StubExecutor(
        result=QueryResult(
            columns=("?column?",), rows=((1,),), truncated=False, row_count=1
        )
    )
    assert handle_execute_sql("SELECT 1", _closed_config(), stub) == {
        "columns": ["?column?"],
        "rows": [(1,)],
        "truncated": False,
        "row_count": 1,
    }
    assert stub.calls == [{"sql": "SELECT 1", "read_only": True}]


def test_allowed_write_runs_read_write_and_reports_rowcount():
    stub = StubExecutor(
        result=QueryResult(columns=(), rows=(), truncated=False, row_count=1)
    )
    assert handle_execute_sql("INSERT INTO t VALUES (1)", _open_config(), stub) == {
        "columns": [],
        "rows": [],
        "truncated": False,
        "row_count": 1,
    }
    assert stub.calls == [{"sql": "INSERT INTO t VALUES (1)", "read_only": False}]


def test_denied_write_raises_verbatim_denial_without_touching_the_executor():
    stub = StubExecutor(
        result=QueryResult(columns=(), rows=(), truncated=False, row_count=0)
    )
    with pytest.raises(
        ToolError,
        match=r"^rejected: InsertStmt is not allowed while PG_ALLOW_WRITES is closed$",
    ):
        handle_execute_sql("INSERT INTO t VALUES (1)", _closed_config(), stub)
    assert stub.calls == []


def test_pg_failure_raises_sqlstate_envelope():
    error = _pg_error("permission denied for table cuenta_p07", "42501")
    stub = StubExecutor(error=error)
    with pytest.raises(
        ToolError, match=r"^42501 permission denied for table cuenta_p07$"
    ):
        handle_execute_sql("INSERT INTO cuenta_p07 VALUES (1)", _open_config(), stub)


def test_failure_without_sqlstate_uses_question_mark():
    stub = StubExecutor(error=RuntimeError("boom"))
    with pytest.raises(ToolError, match=r"^\? boom$"):
        handle_execute_sql("SELECT 1", _closed_config(), stub)
