"""E2E write gate: real PG18 over stdio, through the real composition root.

Covers ``uc-write-denied-default``, ``uc-write-smuggled``,
``uc-dangerous-function``, ``uc-write-allowed-when-open`` and
``uc-single-statement``, positive and negative — 10 scenarios. Denials never
reach the server: both transports classify first, so the pair helper asserts
the verbatim denial in-process (``ToolError``) and over stdio (``isError``).
"""

import pytest

from .conftest import (
    E2EDb,
    assert_fail_pair,
    assert_ok_pair,
    local,
    set_env,
    wire_data,
    wire_server,
    wire_text,
)

CLOSED = "is not allowed while PG_ALLOW_WRITES is closed"


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
async def test_e2e_write_denied_default_pos(
    e2e_db: E2EDb, monkeypatch: pytest.MonkeyPatch, sql: str, node: str
) -> None:
    env = e2e_db.env()
    set_env(monkeypatch, env)
    async with wire_server(env) as call:
        await assert_fail_pair(sql, call, f"rejected: {node} {CLOSED}")


@pytest.mark.parametrize(
    ("sql", "node"),
    [
        ("/* hidden */ INSERT INTO t VALUES (1)", "InsertStmt"),
        ("INSERT /* mid */ INTO t VALUES (1)", "InsertStmt"),
        ("UPDATE /* mid */ t SET a = 1", "UpdateStmt"),
    ],
)
async def test_e2e_write_denied_default_neg(
    e2e_db: E2EDb, monkeypatch: pytest.MonkeyPatch, sql: str, node: str
) -> None:
    env = e2e_db.env()
    set_env(monkeypatch, env)
    async with wire_server(env) as call:
        await assert_fail_pair(sql, call, f"rejected: {node} {CLOSED}")


@pytest.mark.parametrize(
    ("sql", "denial"),
    [
        ("WITH x AS (DELETE FROM t RETURNING *) SELECT * FROM x", "DeleteStmt"),
        (
            "WITH x AS (INSERT INTO t VALUES (1) RETURNING *) SELECT * FROM x",
            "InsertStmt",
        ),
        ("SELECT * INTO n FROM t", "IntoClause"),
        ("SELECT * FROM t FOR UPDATE", "LockingClause"),
        ("EXPLAIN ANALYZE SELECT * FROM t", "ExplainStmt with options"),
        ("EXPLAIN INSERT INTO t VALUES (1)", "InsertStmt"),
        ("SELECT * FROM pg_read_file('pg_hba.conf')", "function pg_read_file"),
    ],
)
async def test_e2e_write_smuggled_pos(
    e2e_db: E2EDb, monkeypatch: pytest.MonkeyPatch, sql: str, denial: str
) -> None:
    env = e2e_db.env()
    set_env(monkeypatch, env)
    async with wire_server(env) as call:
        await assert_fail_pair(sql, call, f"rejected: {denial}")


@pytest.mark.parametrize(
    ("sql", "denial"),
    [
        ("SELECT 1; SELECT 2", "exactly one statement is required, got 2"),
        ("", "exactly one statement is required, got 0"),
        ("   ", "exactly one statement is required, got 0"),
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
async def test_e2e_write_smuggled_neg(
    e2e_db: E2EDb, monkeypatch: pytest.MonkeyPatch, sql: str, denial: str
) -> None:
    env = e2e_db.env()
    set_env(monkeypatch, env)
    async with wire_server(env) as call:
        await assert_fail_pair(sql, call, f"rejected: {denial}")


@pytest.mark.parametrize(
    ("sql", "name"),
    [
        ("SELECT set_config('a', 'b', false)", "set_config"),
        ("SELECT pg_read_file('pg_hba.conf')", "pg_read_file"),
        ("SELECT pg_ls_dir('.')", "pg_ls_dir"),
        ("SELECT lo_creat(-1)", "lo_creat"),
        ("SELECT dblink('a', 'b')", "dblink"),
        ("SELECT currval('s_seq')", "currval"),
        ("SELECT nextval('s_seq')", "nextval"),
    ],
)
async def test_e2e_dangerous_function_pos(
    e2e_db: E2EDb, monkeypatch: pytest.MonkeyPatch, sql: str, name: str
) -> None:
    env = e2e_db.env()
    set_env(monkeypatch, env)
    async with wire_server(env) as call:
        await assert_fail_pair(sql, call, f"rejected: function {name} {CLOSED}")


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
async def test_e2e_dangerous_function_neg(
    e2e_db: E2EDb, monkeypatch: pytest.MonkeyPatch, sql: str, name: str
) -> None:
    env = e2e_db.env()
    set_env(monkeypatch, env)
    async with wire_server(env) as call:
        await assert_fail_pair(sql, call, f"rejected: function {name} {CLOSED}")


async def test_e2e_write_allowed_when_open_pos(
    e2e_db: E2EDb, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A granted write applies through each transport; each cycle cleans
    itself (writes are not idempotent, so the two transports run separate
    insert/delete cycles rather than one shared pair)."""
    env = e2e_db.env(allow_writes=True)
    set_env(monkeypatch, env)
    e2e_db.grant()
    try:
        assert (await local("INSERT INTO public.pgmcp_e2e_scratch VALUES (42)"))[
            "row_count"
        ] == 1
        assert (await local("DELETE FROM public.pgmcp_e2e_scratch WHERE n = 42"))[
            "row_count"
        ] == 1
        async with wire_server(env) as call:
            inserted = await call("INSERT INTO public.pgmcp_e2e_scratch VALUES (42)")
            assert inserted.is_error is False, wire_text(inserted)
            assert wire_data(inserted)["row_count"] == 1
            deleted = await call("DELETE FROM public.pgmcp_e2e_scratch WHERE n = 42")
            assert deleted.is_error is False, wire_text(deleted)
            assert wire_data(deleted)["row_count"] == 1
    finally:
        e2e_db.revoke()


@pytest.mark.parametrize(
    ("sql", "denial"),
    [
        ("SELECT pg_terminate_backend(1)", "function pg_terminate_backend"),
        ("SELECT set_config('a','b',false)", "function set_config"),
        ("BEGIN", "TransactionStmt"),
        ("SET statement_timeout = 0", "VariableSetStmt"),
        ("DISCARD ALL", "DiscardStmt"),
        ("DO $$ BEGIN RAISE NOTICE 'hi'; END $$", "DoStmt"),
    ],
)
async def test_e2e_write_allowed_when_open_neg(
    e2e_db: E2EDb, monkeypatch: pytest.MonkeyPatch, sql: str, denial: str
) -> None:
    """The open gate lifts only the statement allowlist: the denylist and
    the transaction/session statements stay denied in both gates."""
    env = e2e_db.env(allow_writes=True)
    set_env(monkeypatch, env)
    async with wire_server(env) as call:
        await assert_fail_pair(sql, call, f"rejected: {denial}")


async def test_e2e_single_statement_pos(
    e2e_db: E2EDb, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = e2e_db.env()
    set_env(monkeypatch, env)
    async with wire_server(env) as call:
        got = await assert_ok_pair("SELECT 1", call)
    assert got["rows"] == [[1]]


async def test_e2e_single_statement_neg(
    e2e_db: E2EDb, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = e2e_db.env()
    set_env(monkeypatch, env)
    async with wire_server(env) as call:
        await assert_fail_pair(
            "SELECT 1; SELECT 2",
            call,
            "rejected: exactly one statement is required, got 2",
        )
        assert (await local("SELECT 1"))["rows"] == [[1]]
        assert wire_data(await call("SELECT 1"))["rows"] == [[1]]
