"""E2E read path: real PG18 over stdio, through the real composition root.

Covers ``uc-read-ok``, ``uc-read-catalog``, ``uc-read-capped`` and
``uc-read-timeout``, positive and negative — 8 scenarios. Every scenario runs
twice against the same state: in-process through ``build_server`` (what the
coverage gate measures) and over stdio through the official MCP client
spawning ``uv run postgres-mcp`` with real env (the transport proof).
"""

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from postgres_mcp.infrastructure.adapters.postgres import ROW_CAP

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

TABLE_REF = "public.pgmcp_e2e_scratch"


@pytest.mark.parametrize(
    ("sql", "rows"),
    [
        ("SELECT 1", [[1]]),
        (f"TABLE {TABLE_REF}", [[1]]),
        ("VALUES (1)", [[1]]),
        ("WITH x AS (SELECT 1) SELECT * FROM x", [[1]]),
        ("SELECT upper('a')", [["A"]]),
        ("EXPLAIN SELECT 1", None),
    ],
)
async def test_e2e_read_ok_pos(
    e2e_db: E2EDb, monkeypatch: pytest.MonkeyPatch, sql: str, rows: list | None
) -> None:
    env = e2e_db.env()
    set_env(monkeypatch, env)
    async with wire_server(env) as call:
        got = await assert_ok_pair(sql, call)
    if rows is not None:
        assert got["rows"] == rows
    else:
        assert got["row_count"] >= 1  # type: ignore[operator]
    assert got["truncated"] is False


async def test_e2e_read_ok_neg(monkeypatch: pytest.MonkeyPatch) -> None:
    """An unreachable host fails with a connection error; nothing runs.

    Fake sentinels (hermetic): no PG is touched, only the refused TCP
    connect, which carries no sqlstate — the envelope keeps the bare
    ``connection failed`` text.
    """
    env = {
        "PG_HOST": "127.0.0.1",
        "PG_PORT": "54999",
        "PG_USER": "noone",
        "PG_PASSWORD": "wrong",
    }
    set_env(monkeypatch, env)
    async with wire_server(env) as call:
        await assert_fail_pair("SELECT 1", call, "Connection refused")


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT table_name FROM information_schema.tables LIMIT 5",
        "SELECT column_name FROM information_schema.columns LIMIT 5",
    ],
)
async def test_e2e_read_catalog_pos(
    e2e_db: E2EDb, monkeypatch: pytest.MonkeyPatch, sql: str
) -> None:
    env = e2e_db.env()
    set_env(monkeypatch, env)
    async with wire_server(env) as call:
        got = await assert_ok_pair(sql, call)
    assert len(got["rows"]) >= 1  # type: ignore[arg-type]


async def test_e2e_read_catalog_neg(
    e2e_db: E2EDb, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = e2e_db.env()
    set_env(monkeypatch, env)
    async with wire_server(env) as call:
        await assert_fail_pair(
            "SELECT FROM WHERE (((", call, "rejected: could not parse SQL:"
        )


async def test_e2e_read_capped_pos(
    e2e_db: E2EDb, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = e2e_db.env()
    set_env(monkeypatch, env)
    async with wire_server(env) as call:
        got = await assert_ok_pair("SELECT generate_series(1, 2000) AS n", call)
    assert ROW_CAP == 500
    assert len(got["rows"]) == ROW_CAP  # type: ignore[arg-type]
    assert got["truncated"] is True
    assert got["row_count"] == ROW_CAP


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT /* bypass */ generate_series(1, 2000) AS n",
        "SELECT generate_series(1, 2000) AS n -- trailing comment bypass",
    ],
)
async def test_e2e_read_capped_neg(
    e2e_db: E2EDb, monkeypatch: pytest.MonkeyPatch, sql: str
) -> None:
    env = e2e_db.env()
    set_env(monkeypatch, env)
    async with wire_server(env) as call:
        got = await assert_ok_pair(sql, call)
    assert got["truncated"] is True
    assert len(got["rows"]) == ROW_CAP  # type: ignore[arg-type]


async def test_e2e_read_timeout_pos(
    e2e_db: E2EDb, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = e2e_db.env()
    set_env(monkeypatch, env)
    async with wire_server(env) as call:
        got = await assert_ok_pair("SELECT 1", call)
    assert got["rows"] == [[1]]


async def test_e2e_read_timeout_neg(
    e2e_db: E2EDb, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A slow but allowed ``SELECT`` aborts with 57014 after TIMEOUT_MS.

    ``pg_sleep`` cannot be the vehicle: the classifier denies it in both
    gates, so the slow vehicle is a heavy ``count``. The client waits past
    the 15 s server budget.
    """
    env = e2e_db.env()
    set_env(monkeypatch, env)
    sql = "SELECT count(*) FROM generate_series(1, 10000000000)"
    with pytest.raises(ToolError) as excinfo:
        await local(sql)
    assert "57014" in str(excinfo.value)
    async with wire_server(env) as call:
        result = await call(sql, 120.0)
        assert result.is_error is True
        text = wire_text(result)
        assert "57014" in text
        assert "statement timeout" in text
        followup = await call("SELECT 1")
        assert followup.is_error is False
        assert wire_data(followup)["rows"] == [[1]]
