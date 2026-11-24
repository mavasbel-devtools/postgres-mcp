"""Live read-path suite: real PG18, ``postgres`` database only.

Covers ``uc-read-ok``, ``uc-read-catalog``, ``uc-read-capped`` and
``uc-read-timeout``, positive and negative. Reads run through the real
stack as the revoked test role; the classifier-bypassed probes (stacked
input, ``pg_sleep``) call the executor directly, because the classifier
rejects them in both gates and they can never go through the tool.
"""

import psycopg
import pytest
from mcp.server.mcpserver.exceptions import ToolError

from postgres_mcp.domain.config import load_config
from postgres_mcp.infrastructure.adapters.postgres import ROW_CAP, PsycopgExecutor
from postgres_mcp.infrastructure.adapters.stdio import handle_execute_sql

from ..conftest import TABLE, LiveDb


def test_live_read_ok_pos(live: LiveDb) -> None:
    assert live.call("SELECT 1")["rows"] == [(1,)]
    assert live.call(f"TABLE public.{TABLE}")["rows"] == [(1,)]
    assert live.call("VALUES (1)")["rows"] == [(1,)]


def test_live_read_ok_neg() -> None:
    """An unreachable host fails with a connection error; nothing runs.

    Diverges from the component fake on purpose: a real refused TCP
    connect carries no sqlstate, so the envelope is ``? connection
    failed: ... Connection refused``, not ``08001``.
    """
    config = load_config(
        {"PG_USER": "noone", "PG_PASSWORD": "wrong", "PG_PORT": "54999"}
    )
    with pytest.raises(ToolError) as excinfo:
        handle_execute_sql("SELECT 1", config, PsycopgExecutor(config))
    message = str(excinfo.value)
    assert "connection failed" in message
    assert "Connection refused" in message


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT table_name FROM information_schema.tables LIMIT 5",
        "SELECT column_name FROM information_schema.columns LIMIT 5",
    ],
)
def test_live_read_catalog_pos(live: LiveDb, sql: str) -> None:
    result = live.call(sql)
    assert len(result["rows"]) >= 1  # type: ignore[arg-type]


def test_live_read_catalog_neg(live: LiveDb) -> None:
    with pytest.raises(ToolError) as excinfo:
        live.call("SELECT FROM WHERE (((")
    assert "rejected: could not parse SQL:" in str(excinfo.value)


def test_live_read_capped_pos(live: LiveDb) -> None:
    result = live.call("SELECT generate_series(1, 2000) AS n")
    assert result["rows"] is not None
    assert len(result["rows"]) == ROW_CAP  # type: ignore[arg-type]
    assert ROW_CAP == 500
    assert result["truncated"] is True
    assert result["row_count"] == ROW_CAP


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT /* bypass */ generate_series(1, 2000) AS n",
        "SELECT generate_series(1, 2000) AS n -- trailing comment bypass",
    ],
)
def test_live_read_capped_neg(live: LiveDb, sql: str) -> None:
    result = live.call(sql)
    assert result["truncated"] is True
    assert len(result["rows"]) == ROW_CAP  # type: ignore[arg-type]


def test_live_read_timeout_pos(live: LiveDb) -> None:
    assert live.call("SELECT 1")["rows"] == [(1,)]


def test_live_read_timeout_neg(live: LiveDb) -> None:
    """Classifier bypassed: ``pg_sleep`` is deny-listed in both gates, so
    the slow vehicle calls the executor directly; the server aborts it
    with 57014 after TIMEOUT_MS."""
    with pytest.raises(psycopg.Error) as excinfo:
        live.execute_raw("SELECT pg_sleep(20)", read_only=True)
    assert excinfo.value.sqlstate == "57014"
    assert "statement timeout" in str(excinfo.value)
