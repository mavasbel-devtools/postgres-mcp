"""Component-tier classifier paths no feature scenario reaches (fake executor, no I/O).

The approved feature files bind every use case but never send: an open-gate
session statement (``COMMIT``/``SET``/``DISCARD``/``DO``), a bare ``EXPLAIN``
over a plain select, an ``EXPLAIN`` over a write, or a passing CTE. These
plain tests pin those handler paths so the component tier covers the
classifier fully.
"""

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from postgres_mcp.application.ports import ExecutorPort, QueryResult
from postgres_mcp.domain.config import load_config
from postgres_mcp.infrastructure.adapters.stdio import handle_execute_sql


class StubExecutor(ExecutorPort):
    def __init__(self):
        self.calls = []

    def execute(self, sql: str, read_only: bool) -> QueryResult:
        self.calls.append((sql, read_only))
        return QueryResult(
            columns=("?column?",), rows=((1,),), truncated=False, row_count=1
        )


def _open_config():
    return load_config({"PG_USER": "u", "PG_PASSWORD": "p", "PG_ALLOW_WRITES": "1"})


def _closed_config():
    return load_config({"PG_USER": "u", "PG_PASSWORD": "p"})


@pytest.mark.parametrize(
    ("sql", "node"),
    [
        ("COMMIT", "TransactionStmt"),
        ("SET statement_timeout = 0", "VariableSetStmt"),
        ("DISCARD ALL", "DiscardStmt"),
        ("DO $$ BEGIN RAISE NOTICE 'hi'; END $$", "DoStmt"),
    ],
    ids=["commit", "set", "discard", "do"],
)
def test_open_gate_still_denies_session_statements(sql, node):
    stub = StubExecutor()
    with pytest.raises(
        ToolError,
        match=rf"^rejected: {node} is not allowed while PG_ALLOW_WRITES is closed$",
    ):
        handle_execute_sql(sql, _open_config(), stub)
    assert stub.calls == []


def test_closed_bare_explain_over_plain_select_passes():
    stub = StubExecutor()
    result = handle_execute_sql("EXPLAIN SELECT 1", _closed_config(), stub)
    assert result["rows"] == [(1,)]
    assert stub.calls == [("EXPLAIN SELECT 1", True)]


def test_closed_explain_over_write_names_the_write():
    stub = StubExecutor()
    with pytest.raises(
        ToolError,
        match=r"^rejected: DeleteStmt is not allowed while PG_ALLOW_WRITES is closed$",
    ):
        handle_execute_sql("EXPLAIN DELETE FROM t", _closed_config(), stub)
    assert stub.calls == []


def test_closed_passing_cte_passes():
    stub = StubExecutor()
    result = handle_execute_sql(
        "WITH x AS (SELECT 1) SELECT * FROM x", _closed_config(), stub
    )
    assert result["rows"] == [(1,)]
    assert stub.calls == [("WITH x AS (SELECT 1) SELECT * FROM x", True)]
