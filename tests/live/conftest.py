"""Live-tier shared fixture: real PG18 over TCP as a throwaway read-only role.

Endpoint gate: every suite under ``tests/live/`` is skipped — with the
reason below — when ``docker exec postgres true`` fails, i.e. only when
the container is down. Nothing here is skipped otherwise.

Admin setup uses no stored password: ``docker exec postgres psql
-U postgres`` talks to the container's local socket. The test role
(``pgmcp_live_reader``) gets a random per-run password kept in memory
only; tests connect over TCP ``127.0.0.1:5423`` with real ``PG_*`` values
built in memory. The password never reaches stdout: admin failures are
re-raised with the password redacted, and no test prints env or config.
Only database ``postgres`` is written, and only the two temporary
objects, both dropped ``IF EXISTS`` at teardown (after ``DROP OWNED``,
which is what lets a granted role be dropped at all).
"""

from __future__ import annotations

import secrets
import shutil
import subprocess
from pathlib import Path

import psycopg
import pytest

from postgres_mcp.domain.config import PostgresConfig, load_config
from postgres_mcp.infrastructure.adapters.postgres import PsycopgExecutor
from postgres_mcp.infrastructure.adapters.stdio import handle_execute_sql

ROLE = "pgmcp_live_reader"
TABLE = "pgmcp_live_scratch"
SCHEMA = "public"
DBNAME = "postgres"
HOST = "127.0.0.1"
PORT = 5423
SQL_DIR = Path(__file__).resolve().parents[2] / "sql"

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


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Skip the whole live tier — with its reason — only when down."""
    if not PG_UP:
        for item in items:
            item.add_marker(pytest.mark.skip(reason=REASON_DOWN))


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


class LiveDb:
    """Per-run handle. The password lives only in ``self._password``.

    It is never assigned to a test-local, never printed, and admin
    failures re-raise with it redacted. ``self`` reprs carry no secret.
    """

    def __init__(self, password: str) -> None:
        self._password = password

    def config(self, allow_writes: bool = False) -> PostgresConfig:
        env = {
            "PG_HOST": HOST,
            "PG_PORT": str(PORT),
            "PG_USER": ROLE,
            "PG_PASSWORD": self._password,
            "PG_DBNAME": DBNAME,
        }
        if allow_writes:
            env["PG_ALLOW_WRITES"] = "1"
        return load_config(env)

    def call(self, sql: str, allow_writes: bool = False) -> dict[str, object]:
        """One ``execute_sql`` through the real stack (classifier+executor)."""
        config = self.config(allow_writes)
        return handle_execute_sql(sql, config, PsycopgExecutor(config))

    def execute_raw(self, sql: str, read_only: bool = True):
        """One executor call with the classifier bypassed (single-statement,
        timeout and role-layer probes go through here)."""
        return PsycopgExecutor(self.config(True)).execute(sql, read_only)

    def rw_session(self) -> psycopg.Connection:
        """Raw read-write session as the test role.

        Needed wherever the role layer (42501) is the assertion: with the
        role default ``default_transaction_read_only = on``, an INSERT
        through the executor fails 25006 before grants are even consulted,
        so the grant denial is proven in an explicit ``READ WRITE``
        session — the same mechanics as spike 1.4 row 8.
        """
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

    def show(self, setting: str) -> str:
        conn = psycopg.connect(
            host=HOST,
            port=PORT,
            dbname=DBNAME,
            user=ROLE,
            password=self._password,
            autocommit=True,
        )
        try:
            with conn.cursor() as cur:
                cur.execute(f"SHOW {setting}")
                row = cur.fetchone()
                assert row is not None
                return str(row[0])
        finally:
            conn.close()

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


@pytest.fixture(scope="session")
def live() -> LiveDb:
    """Create the role plus the scratch table; yield the handle; drop both."""
    db = LiveDb(secrets.token_urlsafe(24))
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
