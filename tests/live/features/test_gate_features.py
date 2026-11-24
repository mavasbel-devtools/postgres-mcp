"""Live gate suite: real PG18, ``postgres`` database only.

Covers ``uc-write-denied-default``, ``uc-write-smuggled``,
``uc-dangerous-function``, ``uc-write-allowed-when-open`` and
``uc-single-statement``, positive and negative. Denials never reach the
server, so they run through the real stack with the live role's
credentials; the stacked-input probe bypasses the classifier and calls
the executor directly, proving the server rejects the stack with 42601
even if the gate ever let it through.
"""

import psycopg
import pytest
from mcp.server.mcpserver.exceptions import ToolError

from ..conftest import SCHEMA, TABLE, LiveDb


@pytest.mark.parametrize(
    ("sql", "node"),
    [
        ("INSERT INTO t VALUES (1)", "InsertStmt"),
        ("UPDATE t SET a = 1", "UpdateStmt"),
        ("DELETE FROM t", "DeleteStmt"),
        ("DROP TABLE t", "DropStmt"),
        ("CREATE TABLE t (a int)", "CreateStmt"),
        ("ALTER TABLE t ADD COLUMN b int", "AlterTableStmt"),
    ],
)
def test_live_write_denied_default_pos(live: LiveDb, sql: str, node: str) -> None:
    with pytest.raises(ToolError) as excinfo:
        live.call(sql)
    assert f"rejected: {node} is not allowed while PG_ALLOW_WRITES is closed" in str(
        excinfo.value
    )


@pytest.mark.parametrize(
    ("sql", "node"),
    [
        ("/* hidden */ INSERT INTO t VALUES (1)", "InsertStmt"),
        ("INSERT /* mid */ INTO t VALUES (1)", "InsertStmt"),
        ("UPDATE /* mid */ t SET a = 1", "UpdateStmt"),
    ],
)
def test_live_write_denied_default_neg(live: LiveDb, sql: str, node: str) -> None:
    with pytest.raises(ToolError) as excinfo:
        live.call(sql)
    assert f"rejected: {node} is not allowed while PG_ALLOW_WRITES is closed" in str(
        excinfo.value
    )


@pytest.mark.parametrize(
    ("sql", "denial"),
    [
        ("WITH x AS (DELETE FROM t RETURNING *) SELECT * FROM x", "DeleteStmt"),
        (
            "WITH x AS (INSERT INTO t VALUES (1) RETURNING *) SELECT * FROM x",
            "InsertStmt",
        ),
        (
            "WITH x AS (UPDATE t SET a = 1 RETURNING *) SELECT * FROM x",
            "UpdateStmt",
        ),
        (
            "WITH x AS (DELETE /* hidden */ FROM t RETURNING *) SELECT * FROM x",
            "DeleteStmt",
        ),
        ("SELECT * INTO n FROM t", "IntoClause"),
        ("SELECT 'INTO' INTO n FROM t", "IntoClause"),
        ("SELECT * FROM t FOR UPDATE", "LockingClause"),
        ("SELECT * FROM t FOR UPDATE /* trailing */", "LockingClause"),
        ("EXPLAIN ANALYZE SELECT * FROM t", "ExplainStmt with options"),
        ("EXPLAIN /* comment */ ANALYZE SELECT * FROM t", "ExplainStmt with options"),
        ("SELECT * FROM pg_read_file('pg_hba.conf')", "function pg_read_file"),
    ],
)
def test_live_write_smuggled_pos(live: LiveDb, sql: str, denial: str) -> None:
    with pytest.raises(ToolError) as excinfo:
        live.call(sql)
    assert f"rejected: {denial}" in str(excinfo.value)


@pytest.mark.parametrize(
    ("sql", "denial"),
    [
        ("SELECT 1; DELETE FROM t", "exactly one statement is required, got 2"),
        (
            "SELECT 1; SELECT 2 -- stacked read-smuggled stack",
            "exactly one statement is required, got 2",
        ),
        ("COPY t FROM PROGRAM 'id'", "CopyStmt"),
        ("SET statement_timeout = 0", "VariableSetStmt"),
        ("SET TRANSACTION READ WRITE", "VariableSetStmt"),
        ("DO $$ BEGIN RAISE NOTICE 'hi'; END $$", "DoStmt"),
        ("CALL p_procedure()", "CallStmt"),
        ("MERGE INTO t USING s ON t.a = s.a WHEN MATCHED THEN DELETE", "MergeStmt"),
        ("TRUNCATE t", "TruncateStmt"),
        ("GRANT SELECT ON t TO readonly_mcp", "GrantStmt"),
    ],
)
def test_live_write_smuggled_neg(live: LiveDb, sql: str, denial: str) -> None:
    with pytest.raises(ToolError) as excinfo:
        live.call(sql)
    assert f"rejected: {denial}" in str(excinfo.value)


@pytest.mark.parametrize(
    ("sql", "name"),
    [
        ("SELECT set_config('a', 'b', false)", "set_config"),
        ("SELECT pg_read_file('pg_hba.conf')", "pg_read_file"),
        ("SELECT pg_ls_dir('.')", "pg_ls_dir"),
        ("SELECT lo_creat(-1)", "lo_creat"),
        ("SELECT nextval('s_seq')", "nextval"),
    ],
)
def test_live_dangerous_function_pos(live: LiveDb, sql: str, name: str) -> None:
    with pytest.raises(ToolError) as excinfo:
        live.call(sql)
    assert (
        f"rejected: function {name} is not allowed while PG_ALLOW_WRITES is closed"
        in str(excinfo.value)
    )


@pytest.mark.parametrize(
    ("sql", "name"),
    [
        ("SELECT pg_sleep(0.1)", "pg_sleep"),
        ("SELECT * FROM pg_sleep(0.1)", "pg_sleep"),
        ("SELECT * FROM pg_catalog.pg_read_file('x')", "pg_read_file"),
        ("SELECT pg_terminate_backend(1)", "pg_terminate_backend"),
        ("SELECT PG_SLEEP(0.1)", "pg_sleep"),
    ],
)
def test_live_dangerous_function_neg(live: LiveDb, sql: str, name: str) -> None:
    with pytest.raises(ToolError) as excinfo:
        live.call(sql)
    assert (
        f"rejected: function {name} is not allowed while PG_ALLOW_WRITES is closed"
        in str(excinfo.value)
    )


def test_live_write_allowed_when_open_pos(live: LiveDb) -> None:
    live.grant()
    try:
        result = live.call(
            f"INSERT INTO {SCHEMA}.{TABLE} VALUES (42)", allow_writes=True
        )
        assert result["row_count"] == 1
    finally:
        live.call(f"DELETE FROM {SCHEMA}.{TABLE} WHERE n = 42", allow_writes=True)
        live.revoke()


@pytest.mark.parametrize(
    ("sql", "name"),
    [
        ("SELECT pg_terminate_backend(1)", "pg_terminate_backend"),
        ("SELECT set_config('a','b',false)", "set_config"),
    ],
)
def test_live_write_allowed_when_open_neg(live: LiveDb, sql: str, name: str) -> None:
    with pytest.raises(ToolError) as excinfo:
        live.call(sql, allow_writes=True)
    assert (
        f"rejected: function {name} is not allowed while PG_ALLOW_WRITES is closed"
        in str(excinfo.value)
    )


def test_live_single_statement_pos(live: LiveDb) -> None:
    assert live.call("SELECT 1")["rows"] == [(1,)]


def test_live_single_statement_neg(live: LiveDb) -> None:
    """Classifier bypassed: the stack goes straight to the executor, and
    the server rejects it with 42601 — nothing in the stack runs, so the
    follow-up SELECT still serves."""
    with pytest.raises(psycopg.Error) as excinfo:
        live.execute_raw("SELECT 1; SELECT 2", read_only=True)
    assert excinfo.value.sqlstate == "42601"
    assert "multiple commands" in str(excinfo.value)
    assert live.execute_raw("SELECT 1", read_only=True).rows == ((1,),)
