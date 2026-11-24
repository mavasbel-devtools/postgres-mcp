"""E2E shared fixtures: real PG18 through the real composition root.

Every PG-backed test runs each scenario twice against the same database
state: once in-process through :func:`build_server` (the real composition
root, which is what the coverage gate measures) and once over stdio through
the official MCP client (``ClientSession`` + ``stdio_client`` spawning
``uv run postgres-mcp`` with real env — the transport proof).

Endpoint gate: the ``e2e_db`` fixture skips with its reason only when
``docker exec postgres true`` fails, i.e. only when the container is down.
Hermetic tests (bad env, ``main`` wiring) use fake sentinels and never touch
the network, so they run even then.

Admin setup mirrors the live tier: ``docker exec postgres psql -U postgres``
on the container's local socket, a random per-run password kept in memory
only, TCP ``127.0.0.1:5423``, database ``postgres`` only, and the two
temporary objects (``pgmcp_e2e_*``, never the live tier's ``pgmcp_live_*``
names) dropped ``IF EXISTS`` at teardown. The password never reaches stdout:
admin failures are re-raised with it redacted.
"""

from __future__ import annotations

import json
import secrets
import shutil
import subprocess
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

import psycopg
import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult

from postgres_mcp.main.server import build_server

ROLE = "pgmcp_e2e_reader"
TABLE = "pgmcp_e2e_scratch"
SCHEMA = "public"
DBNAME = "postgres"
HOST = "127.0.0.1"
PORT = 5423
WORKTREE = Path(__file__).resolve().parents[2]
SQL_DIR = WORKTREE / "sql"

REASON_DOWN = "postgres container unreachable: `docker exec postgres true` failed"


def _container_up() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        subprocess.run(
            ["docker", "exec", "postgres", "true"],
            capture_output=True,
            timeout=10,
            check=True,
        )
    except (subprocess.SubprocessError, OSError):
        return False
    return True


PG_UP = _container_up()


def _redact(text: str, password: str) -> str:
    return text.replace(password, "***") if password else text


def _admin_argv() -> list[str]:
    return [
        "docker",
        "exec",
        "-i",
        "postgres",
        "psql",
        "-U",
        "postgres",
        "-d",
        DBNAME,
        "-v",
        "ON_ERROR_STOP=1",
        "-q",
    ]


class E2EDb:
    """Per-run handle. The password lives only in ``self._password``."""

    def __init__(self, password: str) -> None:
        self._password = password

    def env(self, allow_writes: bool = False) -> dict[str, str]:
        """Real ``PG_*`` values, built in memory for one server or client."""
        env = {
            "PG_HOST": HOST,
            "PG_PORT": str(PORT),
            "PG_USER": ROLE,
            "PG_PASSWORD": self._password,
            "PG_DBNAME": DBNAME,
        }
        if allow_writes:
            env["PG_ALLOW_WRITES"] = "1"
        return env

    def admin(self, statements: str) -> None:
        proc = subprocess.run(
            _admin_argv() + ["-tA"],
            input=statements,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if proc.returncode != 0:
            raise AssertionError(f"admin SQL failed: {proc.stderr.strip()[-2000:]}")

    def run_script(self, name: str, variables: dict[str, str]) -> None:
        """Run one ``sql/`` script with psql variables (password redacted)."""
        sql = (SQL_DIR / name).read_text(encoding="utf-8")
        argv = _admin_argv()
        for key, value in variables.items():
            argv += ["-v", f"{key}={value}"]
        argv += ["-f", "-"]
        try:
            proc = subprocess.run(
                argv, input=sql, capture_output=True, text=True, timeout=60
            )
        except Exception as exc:
            raise AssertionError(
                f"admin {name} failed to run: {_redact(str(exc), self._password)}"
            ) from exc
        if proc.returncode != 0:
            raise AssertionError(
                f"admin {name} failed: "
                f"{_redact(proc.stderr.strip()[-2000:], self._password)}"
            )

    def grant(self) -> None:
        self.run_script(
            "grant_writes.sql", {"role": ROLE, "table": f"{SCHEMA}.{TABLE}"}
        )

    def revoke(self) -> None:
        self.run_script(
            "revoke_writes.sql", {"role": ROLE, "table": f"{SCHEMA}.{TABLE}"}
        )

    def rw_session(self) -> psycopg.Connection:
        """Raw read-write session as the test role (role-layer 42501 proof)."""
        conn = psycopg.connect(
            host=HOST,
            port=PORT,
            dbname=DBNAME,
            user=ROLE,
            password=self._password,
            autocommit=True,
        )
        conn.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ WRITE")
        return conn


@pytest.fixture(scope="session")
def e2e_db() -> E2EDb:
    """Create the role plus the scratch table; yield the handle; drop both."""
    if not PG_UP:
        pytest.skip(REASON_DOWN)
    db = E2EDb(secrets.token_urlsafe(24))
    try:
        db.run_script(
            "create_readonly_role.sql",
            {"role": ROLE, "password": db._password, "schema": SCHEMA},
        )
        db.admin(
            f"CREATE TABLE IF NOT EXISTS {SCHEMA}.{TABLE}(n integer);"
            f"DELETE FROM {SCHEMA}.{TABLE};"
            f"INSERT INTO {SCHEMA}.{TABLE} VALUES (1);"
        )
    except Exception:
        db.admin(
            f"REASSIGN OWNED BY {ROLE} TO postgres;"
            f"DROP OWNED BY {ROLE};"
            f"DROP TABLE IF EXISTS {SCHEMA}.{TABLE};"
            f"DROP ROLE IF EXISTS {ROLE};"
        )
        raise
    yield db
    db.admin(
        f"REASSIGN OWNED BY {ROLE} TO postgres;"
        f"DROP OWNED BY {ROLE};"
        f"DROP TABLE IF EXISTS {SCHEMA}.{TABLE};"
        f"DROP ROLE IF EXISTS {ROLE};"
    )


_PG_KEYS = (
    "PG_HOST",
    "PG_PORT",
    "PG_USER",
    "PG_PASSWORD",
    "PG_DBNAME",
    "PG_ALLOW_WRITES",
)


def set_env(monkeypatch: pytest.MonkeyPatch, env: dict[str, str]) -> None:
    """Start from a blank ``PG_*`` slate (hermetic pattern), then set ``env``."""
    for key in _PG_KEYS:
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)


async def local(sql: str) -> dict[str, object]:
    """One ``execute_sql`` through the real composition root, in-process.

    Returns the parsed JSON result set. Raises :class:`ToolError` on denial
    or PG error, like the unit tier.
    """
    server = build_server()
    result = await server.call_tool("execute_sql", {"sql": sql})
    assert result.is_error is False
    assert len(result.content) == 1
    text = getattr(result.content[0], "text", "")
    return json.loads(text)


@asynccontextmanager
async def wire_server(
    env: dict[str, str],
) -> AsyncIterator[Callable[[str], Awaitable[CallToolResult]]]:
    """One official-client session over stdio against ``uv run postgres-mcp``.

    Yields a ``call(sql, *, read_timeout=None)`` coroutine. PG errors and
    denials arrive as ``is_error`` results (the MCP wire shape), never raised.
    """
    params = StdioServerParameters(
        command=shutil.which("uv") or "uv",
        args=["run", "postgres-mcp"],
        env=env,
        cwd=str(WORKTREE),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            async def call(
                sql: str, read_timeout: float | None = None
            ) -> CallToolResult:
                kwargs: dict[str, object] = {}
                if read_timeout is not None:
                    kwargs["read_timeout_seconds"] = read_timeout
                return await session.call_tool(
                    "execute_sql",
                    {"sql": sql},
                    **kwargs,  # type: ignore[arg-type]
                )

            yield call


def wire_text(result: CallToolResult) -> str:
    """All text payloads of one wire result, for ``in`` assertions."""
    return "\n".join(getattr(item, "text", "") for item in result.content)


def wire_data(result: CallToolResult) -> dict[str, object]:
    """The JSON result-set payload of a successful wire call."""
    return json.loads(wire_text(result))


async def assert_ok_pair(
    sql: str,
    call: Callable[[str], Awaitable[CallToolResult]],
    read_timeout: float | None = None,
) -> dict[str, object]:
    """The same read succeeds in-process and over stdio with identical rows."""
    got_local = await local(sql)
    got_wire = await call(sql, read_timeout) if read_timeout else await call(sql)
    assert got_wire.is_error is False, wire_text(got_wire)
    data = wire_data(got_wire)
    assert data["rows"] == got_local["rows"]
    assert data["truncated"] == got_local["truncated"]
    assert data["row_count"] == got_local["row_count"]
    return got_local


async def assert_fail_pair(
    sql: str,
    call: Callable[[str], Awaitable[CallToolResult]],
    text: str,
    read_timeout: float | None = None,
) -> None:
    """The same call fails in-process (``ToolError``) and over stdio.

    Both envelopes mention ``text``: denials verbatim, PG errors by code.
    """
    with pytest.raises(ToolError) as excinfo:
        await local(sql)
    assert text in str(excinfo.value)
    got_wire = await call(sql, read_timeout) if read_timeout else await call(sql)
    assert got_wire.is_error is True, wire_text(got_wire)
    assert text in wire_text(got_wire)
