"""Live role suite: real PG18, ``postgres`` database only.

Covers ``uc-role-readonly`` and ``uc-role-grant-revoke``, positive and
negative, including the 42501 → success → 42501 cycle around grant and
revoke that the operator guide quotes.

The role default is ``default_transaction_read_only = on`` (set by
``create_readonly_role.sql``), so a plain INSERT through the executor
fails 25006 before grants are even consulted. The grant denial is
therefore proven in an explicit ``READ WRITE`` session — the same
mechanics as spike 1.4 row 8 — while reads and the granted write go
through the real ``execute_sql`` stack.
"""

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from postgres_mcp.domain.config import load_config
from postgres_mcp.infrastructure.adapters.postgres import PsycopgExecutor
from postgres_mcp.infrastructure.adapters.stdio import handle_execute_sql

from ..conftest import SCHEMA, TABLE, LiveDb


def test_live_role_readonly_pos(live: LiveDb) -> None:
    live.revoke()
    assert live.call("SELECT 1")["rows"] == [(1,)]
    conn = live.rw_session()
    try:
        with conn.cursor() as cur:
            with pytest.raises(Exception) as excinfo:
                cur.execute(f"INSERT INTO {SCHEMA}.{TABLE} VALUES (1)")
        assert excinfo.value.sqlstate == "42501"  # type: ignore[attr-defined]
        assert f"permission denied for table {TABLE}" in str(excinfo.value)
    finally:
        conn.close()


def test_live_role_readonly_neg(live: LiveDb) -> None:
    """A wrong password fails authentication; nothing runs.

    Diverges from the component fake on purpose: a real refused TCP
    login carries no sqlstate, so the envelope keeps the server's
    ``password authentication failed`` text without a ``28P01`` code.
    """
    config = load_config(
        {
            "PG_HOST": "127.0.0.1",
            "PG_PORT": "5423",
            "PG_USER": "pgmcp_live_reader",
            "PG_PASSWORD": "wrong-password",
            "PG_DBNAME": "postgres",
        }
    )
    with pytest.raises(ToolError) as excinfo:
        handle_execute_sql("SELECT 1", config, PsycopgExecutor(config))
    message = str(excinfo.value)
    assert "password authentication failed" in message
    assert "pgmcp_live_reader" in message


def test_live_role_grant_revoke_cycle(live: LiveDb) -> None:
    """42501 → success → 42501 around grant and revoke (guide verbatim)."""
    live.revoke()
    assert live.show("default_transaction_read_only") == "on"

    conn = live.rw_session()
    try:
        with conn.cursor() as cur:
            with pytest.raises(Exception) as excinfo:
                cur.execute(f"INSERT INTO {SCHEMA}.{TABLE} VALUES (1)")
        assert excinfo.value.sqlstate == "42501"  # type: ignore[attr-defined]
        denial_before = str(excinfo.value).strip().splitlines()[0]
        print(f"LIVE-CYCLE step1: 42501 {denial_before}")
    finally:
        conn.close()

    live.grant()
    assert live.show("default_transaction_read_only") == "off"
    result = live.call(f"INSERT INTO {SCHEMA}.{TABLE} VALUES (99)", allow_writes=True)
    assert result["row_count"] == 1
    print(f"LIVE-CYCLE step2: INSERT 0 1 (row_count {result['row_count']})")

    conn = live.rw_session()
    try:
        with conn.cursor() as cur:
            cur.execute(f"UPDATE {SCHEMA}.{TABLE} SET n = 100 WHERE n = 99")
            assert cur.rowcount == 1
            cur.execute(f"DELETE FROM {SCHEMA}.{TABLE} WHERE n = 100")
            assert cur.rowcount == 1
    finally:
        conn.close()

    live.revoke()
    assert live.show("default_transaction_read_only") == "on"

    conn = live.rw_session()
    try:
        with conn.cursor() as cur:
            with pytest.raises(Exception) as excinfo:
                cur.execute(f"INSERT INTO {SCHEMA}.{TABLE} VALUES (1)")
        assert excinfo.value.sqlstate == "42501"  # type: ignore[attr-defined]
        denial_after = str(excinfo.value).strip().splitlines()[0]
        print(f"LIVE-CYCLE step3: 42501 {denial_after}")
    finally:
        conn.close()

    assert "permission denied" in denial_before
    assert f"permission denied for table {TABLE}" in denial_after
    assert live.call(f"TABLE {SCHEMA}.{TABLE}")["rows"] == [(1,)]
