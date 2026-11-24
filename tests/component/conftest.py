"""Component-tier shared steps and scripted fakes (no I/O, no socket).

Every feature scenario in ``tests/features/`` runs here against
:class:`FakeExecutor`, a scripted :class:`ExecutorPort` double:

- plain ``SELECT`` returns one ``(1,)`` row;
- ``information_schema`` queries return two canned catalog rows;
- ``generate_series`` over-cap queries return ``ROW_CAP`` rows flagged
  ``truncated`` (the real capping is proven in ``test_postgres_executor.py``;
  here the handler passthrough is what is asserted);
- ``INSERT`` succeeds with ``row_count 1`` unless the grant was revoked, in
  which case it raises ``42501``, or a failure was injected (unreachable host
  ``08001``, wrong password ``28P01``, timed-out query ``57014``).

The ``readonly_mcp`` role givens imply the gate is open: the scenarios expect
a revoked ``INSERT`` to fail with ``42501`` from the role, which the
classifier can only reach when the gate lets the statement through (the role
is the final layer, not the first).
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import psycopg
import pytest
from mcp.server.mcpserver.exceptions import ToolError
from pytest_bdd import given, then, when
from pytest_bdd.parsers import parse

from postgres_mcp.application.ports import ExecutorPort, QueryResult
from postgres_mcp.domain.config import ConfigError, load_config
from postgres_mcp.infrastructure.adapters.postgres import ROW_CAP
from postgres_mcp.infrastructure.adapters.stdio import handle_execute_sql


def _pg_error(message: str, sqlstate: str) -> psycopg.OperationalError:
    err = psycopg.OperationalError(message)
    err.sqlstate = sqlstate
    return err


class FakeExecutor(ExecutorPort):
    """Scripted port double; records attempts separately from statements that ran."""

    def __init__(self) -> None:
        self.attempts: list[tuple[str, bool]] = []
        self.ran: list[tuple[str, bool]] = []
        self.fail_with: psycopg.Error | None = None
        self.grant_revoked = False

    def execute(self, sql: str, read_only: bool) -> QueryResult:
        self.attempts.append((sql, read_only))
        if self.fail_with is not None:
            raise self.fail_with
        lowered = sql.lower()
        if "generate_series" in lowered:
            rows = tuple((i,) for i in range(1, ROW_CAP + 1))
            result = QueryResult(
                columns=("n",), rows=rows, truncated=True, row_count=ROW_CAP
            )
        elif "information_schema" in lowered:
            result = QueryResult(
                columns=("table_name",),
                rows=(("t_one",), ("t_two",)),
                truncated=False,
                row_count=2,
            )
        elif lowered.lstrip().startswith("insert"):
            if self.grant_revoked:
                raise _pg_error("permission denied for table cuenta_p07", "42501")
            result = QueryResult(columns=(), rows=(), truncated=False, row_count=1)
        else:
            result = QueryResult(
                columns=("?column?",), rows=((1,),), truncated=False, row_count=1
            )
        self.ran.append((sql, read_only))
        return result


class Harness:
    """One scenario's world: env, loaded config (or its error), fake, last call."""

    def __init__(self) -> None:
        self.env: dict[str, str] = {}
        self.config = load_config({"PG_USER": "u", "PG_PASSWORD": "p"})
        self.config_error: ConfigError | None = None
        self.fake = FakeExecutor()
        self.last_result: dict[str, object] | None = None
        self.last_error: ToolError | None = None


@pytest.fixture
def harness() -> Harness:
    return Harness()


def _closed_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = {"PG_USER": "u", "PG_PASSWORD": "p"}
    if extra:
        env.update(extra)
    return env


@given("the gate is closed")
def gate_closed(harness: Harness) -> None:
    harness.config = load_config(_closed_env())
    harness.config_error = None
    harness.fake.fail_with = None
    harness.fake.grant_revoked = False


@then("the gate is closed")
def gate_still_closed(harness: Harness) -> None:
    assert harness.config is not None
    assert harness.config.allow_writes is False


@given("the gate is open")
def gate_open(harness: Harness) -> None:
    harness.config = load_config(_closed_env({"PG_ALLOW_WRITES": "1"}))
    harness.config_error = None
    harness.fake.fail_with = None
    harness.fake.grant_revoked = False


@given("the database host is unreachable")
def host_unreachable(harness: Harness) -> None:
    harness.config = load_config(_closed_env())
    harness.fake.fail_with = _pg_error("host unreachable", "08001")


@given("valid PG_HOST PG_PORT PG_USER PG_PASSWORD env")
def valid_env(harness: Harness) -> None:
    harness.env = {
        "PG_HOST": "127.0.0.1",
        "PG_PORT": "5423",
        "PG_USER": "app_user",
        "PG_PASSWORD": "s3cret",
        "PG_DBNAME": "postgres",
    }


@given(parse("env var {name} is {value}"))
def malformed_env(harness: Harness, name: str, value: str) -> None:
    harness.env = {
        "PG_HOST": "127.0.0.1",
        "PG_PORT": "5423",
        "PG_USER": "app_user",
        "PG_PASSWORD": "s3cret",
        "PG_DBNAME": "postgres",
    }
    cleaned = value.strip('"')
    harness.env[name] = "" if cleaned == "(empty)" else cleaned


@given("the readonly_mcp role with revoked write grants")
def readonly_role(harness: Harness) -> None:
    harness.config = load_config(_closed_env({"PG_ALLOW_WRITES": "1"}))
    harness.fake.grant_revoked = True


@given("the readonly_mcp role with a wrong password in env")
def readonly_role_wrong_password(harness: Harness) -> None:
    harness.config = load_config(_closed_env({"PG_ALLOW_WRITES": "1"}))
    harness.fake.fail_with = _pg_error(
        "password authentication failed for user readonly_mcp", "28P01"
    )


@given("write granted on the exercise table")
def write_granted(harness: Harness) -> None:
    harness.fake.grant_revoked = False


@given("the write grant revoked on the exercise table")
def write_revoked(harness: Harness) -> None:
    harness.fake.grant_revoked = True


@when("the server loads its configuration")
def loads_configuration(harness: Harness) -> None:
    try:
        harness.config = load_config(harness.env)
        harness.config_error = None
    except ConfigError as exc:
        harness.config = None
        harness.config_error = exc


@when(parse('the agent calls "{tool}" with {arguments}'))
def calls_execute_sql(harness: Harness, tool: str, arguments: str) -> None:
    assert tool == "execute_sql", f"unknown tool {tool!r}"
    if arguments == "over-cap SELECT SQL":
        sql = "SELECT generate_series(1, 2000) AS n"
    elif arguments == "slow but allowed SELECT SQL":
        harness.fake.fail_with = _pg_error(
            "canceling statement due to statement timeout", "57014"
        )
        sql = "SELECT count(*) FROM generate_series(1, 100000000)"
    elif arguments in ("granted INSERT SQL", "revoked INSERT SQL"):
        sql = "INSERT INTO cuenta_p07 VALUES (1)"
    else:
        sql = json.loads(arguments)["sql"]
    try:
        harness.last_result = handle_execute_sql(sql, harness.config, harness.fake)
        harness.last_error = None
    except ToolError as exc:
        harness.last_result = None
        harness.last_error = exc


@then("the call succeeds")
def call_succeeds(harness: Harness) -> None:
    assert harness.last_error is None, f"the call failed: {harness.last_error}"
    assert harness.last_result is not None


@then(parse('the call fails mentioning "{text}"'))
def call_fails(harness: Harness, text: str) -> None:
    assert harness.last_error is not None, "the call was expected to fail"
    assert text in str(harness.last_error), f"{harness.last_error} mentions no {text!r}"


@then(parse("the result rows are {rows}"))
def result_rows_are(harness: Harness, rows: str) -> None:
    assert harness.last_result is not None
    assert harness.last_result["rows"] == ast.literal_eval(rows)


@then("no statement ran on the server")
def no_statement_ran(harness: Harness) -> None:
    assert harness.fake.ran == []


@then("the result has at least one row")
def result_has_a_row(harness: Harness) -> None:
    assert harness.last_result is not None
    assert len(harness.last_result["rows"]) >= 1  # type: ignore[arg-type]


@then("the result has exactly ROW_CAP rows")
def result_has_row_cap_rows(harness: Harness) -> None:
    assert harness.last_result is not None
    assert len(harness.last_result["rows"]) == ROW_CAP  # type: ignore[arg-type]


@then(parse('the result field "{name}" is {value}'))
def result_field_is(harness: Harness, name: str, value: str) -> None:
    assert harness.last_result is not None
    assert harness.last_result[name] == json.loads(value)


@then(parse("the result reports row count {count:d}"))
def result_row_count(harness: Harness, count: int) -> None:
    assert harness.last_result is not None
    assert harness.last_result["row_count"] == count


@then(parse('the failure mentions "{text}"'))
def failure_mentions(harness: Harness, text: str) -> None:
    assert harness.last_error is not None
    assert text in str(harness.last_error), f"{harness.last_error} mentions no {text!r}"


@then("the configuration connects to the postgres database")
def configuration_connects(harness: Harness) -> None:
    assert harness.config_error is None, f"the load failed: {harness.config_error}"
    assert harness.config is not None
    assert harness.config.PG_DBNAME == "postgres"
    assert harness.config.PG_HOST == "127.0.0.1"
    assert harness.config.PG_PORT == 5423
    assert harness.config.PG_USER == "app_user"


@then(parse('the load fails mentioning "{error}"'))
def load_fails(harness: Harness, error: str) -> None:
    assert harness.config_error is not None, "the load was expected to fail"
    assert error in str(harness.config_error)


def pytest_configure(config: pytest.Config) -> None:
    """Register the feature-scenario tags, mirroring x-mcp's component conftest."""
    registered: set[str] = set()
    for path in sorted(
        (Path(__file__).resolve().parent.parent / "features").glob("*.feature")
    ):
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped.startswith("@"):
                continue
            for tag in stripped.split():
                name = tag.removeprefix("@")
                if (
                    name.startswith(("feature-", "dependency-", "scenario-"))
                    and name not in registered
                ):
                    kind, _, _ = name.partition("-")
                    registered.add(name)
                    config.addinivalue_line(
                        "markers", f"{name}: the {kind} tag of the feature scenarios"
                    )
