"""E2E config + role layers: real PG18 over stdio, real composition root.

Covers ``uc-config-env`` (positive and negative) plus ``uc-role-readonly``
and ``uc-role-grant-revoke`` (positive and negative) — 6 scenarios.

``uc-config-env-neg`` is hermetic: the bad env never reaches the network.
In-process ``build_server`` raises the fixed ``ConfigError`` text, and the
real ``uv run postgres-mcp`` subprocess exits 2 with the same text as its
only stderr line. ``uc-role-readonly-neg`` uses a wrong password (live
capture): the refused login carries no sqlstate, so the envelope keeps the
server's ``password authentication failed`` text verbatim.
"""

import shutil
import subprocess

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from postgres_mcp.domain.config import ConfigError, load_config
from postgres_mcp.main.server import build_server

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


async def test_e2e_config_env_pos(
    e2e_db: E2EDb, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = e2e_db.env()
    set_env(monkeypatch, env)
    config = load_config(env)
    assert config.PG_HOST == "127.0.0.1"
    assert config.PG_PORT == 5423
    assert config.PG_DBNAME == "postgres"
    assert config.PG_USER == "pgmcp_e2e_reader"
    assert config.allow_writes is False
    async with wire_server(env) as call:
        got = await assert_ok_pair("SELECT 1", call)
    assert got["rows"] == [[1]]


@pytest.mark.parametrize(
    ("name", "value", "error"),
    [
        ("PG_PORT", "abc", "invalid PG_PORT 'abc': must be 1-65535"),
        ("PG_PORT", "99999", "invalid PG_PORT '99999': must be 1-65535"),
        ("PG_HOST", "(empty)", "missing required variable: PG_HOST"),
        ("PG_USER", "(empty)", "missing required variable: PG_USER"),
        ("PG_PASSWORD", "(empty)", "missing required variable: PG_PASSWORD"),
        ("PG_DBNAME", "(empty)", "missing required variable: PG_DBNAME"),
    ],
)
def test_e2e_config_env_neg(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str, error: str
) -> None:
    env = {
        "PG_HOST": "127.0.0.1",
        "PG_PORT": "5423",
        "PG_USER": "app_user",
        "PG_PASSWORD": "s3cret",
        "PG_DBNAME": "postgres",
    }
    env[name] = "" if value == "(empty)" else value
    set_env(monkeypatch, env)
    with pytest.raises(ConfigError) as excinfo:
        build_server()
    assert error in str(excinfo.value)
    proc = subprocess.run(
        [shutil.which("uv") or "uv", "run", "postgres-mcp"],
        input="",
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 2
    assert proc.stdout == ""
    assert proc.stderr == f"postgres-mcp: {error}\n"


async def test_e2e_role_readonly_pos(
    e2e_db: E2EDb, monkeypatch: pytest.MonkeyPatch
) -> None:
    e2e_db.revoke()
    env = e2e_db.env()
    set_env(monkeypatch, env)
    async with wire_server(env) as call:
        got = await assert_ok_pair("SELECT 1", call)
    assert got["rows"] == [[1]]
    conn = e2e_db.rw_session()
    try:
        with conn.cursor() as cur:
            with pytest.raises(Exception) as excinfo:
                cur.execute("INSERT INTO public.pgmcp_e2e_scratch VALUES (1)")
        assert excinfo.value.sqlstate == "42501"  # type: ignore[attr-defined]
        assert "permission denied for table pgmcp_e2e_scratch" in str(excinfo.value)
    finally:
        conn.close()


async def test_e2e_role_readonly_neg(
    e2e_db: E2EDb, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = e2e_db.env()
    env["PG_PASSWORD"] = "wrong-password"
    set_env(monkeypatch, env)
    with pytest.raises(ToolError) as excinfo:
        await local("SELECT 1")
    assert "password authentication failed" in str(excinfo.value)
    assert "pgmcp_e2e_reader" in str(excinfo.value)
    async with wire_server(env) as call:
        result = await call("SELECT 1")
        assert result.is_error is True
        assert "password authentication failed" in wire_text(result)
        assert "pgmcp_e2e_reader" in wire_text(result)


async def test_e2e_role_grant_revoke_pos(
    e2e_db: E2EDb, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Granted writes apply through each transport; each cycle cleans itself
    (writes are not idempotent, so the two transports run separate
    insert/delete cycles rather than one shared pair)."""
    e2e_db.grant()
    try:
        env = e2e_db.env(allow_writes=True)
        set_env(monkeypatch, env)
        assert (await local("INSERT INTO public.pgmcp_e2e_scratch VALUES (99)"))[
            "row_count"
        ] == 1
        assert (await local("DELETE FROM public.pgmcp_e2e_scratch WHERE n = 99"))[
            "row_count"
        ] == 1
        async with wire_server(env) as call:
            inserted = await call("INSERT INTO public.pgmcp_e2e_scratch VALUES (99)")
            assert inserted.is_error is False, wire_text(inserted)
            assert wire_data(inserted)["row_count"] == 1
            deleted = await call("DELETE FROM public.pgmcp_e2e_scratch WHERE n = 99")
            assert deleted.is_error is False, wire_text(deleted)
            assert wire_data(deleted)["row_count"] == 1
    finally:
        e2e_db.revoke()


async def test_e2e_role_grant_revoke_neg(
    e2e_db: E2EDb, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Post-revoke the tool blocks the write twice: the read-only session
    default rejects it with 25006, and an explicit READ WRITE session proves
    the grant itself is gone with the verbatim 42501 observable."""
    e2e_db.revoke()
    env = e2e_db.env(allow_writes=True)
    set_env(monkeypatch, env)
    async with wire_server(env) as call:
        await assert_fail_pair(
            "INSERT INTO public.pgmcp_e2e_scratch VALUES (1)",
            call,
            "25006",
        )
    conn = e2e_db.rw_session()
    try:
        with conn.cursor() as cur:
            with pytest.raises(Exception) as excinfo:
                cur.execute("INSERT INTO public.pgmcp_e2e_scratch VALUES (1)")
        assert excinfo.value.sqlstate == "42501"  # type: ignore[attr-defined]
        assert "permission denied for table pgmcp_e2e_scratch" in str(excinfo.value)
    finally:
        conn.close()
