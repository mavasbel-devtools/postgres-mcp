"""E2E wiring: the composition root's process edges, hermetic (no PG).

``main`` cannot run against live PG in-process — it owns the stdio loop —
so these tests pin its two process edges with fake sentinels: success
delegates to the built server's ``run``, and a missing credential exits 2
with one stderr line and no traceback. The ``ExecutorPort`` stub pins the
seam's contract body. They run even when the container is down.
"""

import pytest
from mcp.server.mcpserver import MCPServer

import postgres_mcp.main.server as server_module
from postgres_mcp.application.ports import ExecutorPort, QueryResult
from postgres_mcp.main.server import build_server, main


def _set_fake_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "PG_HOST",
        "PG_PORT",
        "PG_USER",
        "PG_PASSWORD",
        "PG_DBNAME",
        "PG_ALLOW_WRITES",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("PG_USER", "PG_USER_FAKE")
    monkeypatch.setenv("PG_PASSWORD", "PG_PASSWORD_FAKE")


def test_e2e_main_runs_the_built_server(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_fake_env(monkeypatch)
    calls: list[bool] = []
    monkeypatch.setattr(MCPServer, "run", lambda self, *a, **k: calls.append(True))
    main()
    assert calls == [True]
    assert isinstance(build_server(), MCPServer)


def test_e2e_main_exits_2_with_one_line_and_no_traceback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _set_fake_env(monkeypatch)
    monkeypatch.delenv("PG_USER")
    with pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "postgres-mcp: missing required variable: PG_USER\n"


def test_e2e_executor_port_body_documents_the_contract() -> None:
    class Stub(ExecutorPort):
        def execute(self, sql: str, read_only: bool) -> QueryResult:
            return QueryResult(columns=(), rows=(), truncated=False, row_count=0)

    assert ExecutorPort.execute(Stub(), "SELECT 1", True) is None
    assert server_module.build_server is build_server
