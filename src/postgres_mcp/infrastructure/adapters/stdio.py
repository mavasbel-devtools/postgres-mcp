"""S-in adapter: the single MCP SDK importer in the tree.

One thin handler: classify, then execute, then render. psycopg is
deliberately NOT imported here (dependency table: the driver lives in
``adapters/postgres`` only); executor failures are rendered by duck-typed
``sqlstate`` plus message, so every failure still reaches the client as an
error envelope and the tool never crashes.
"""

from __future__ import annotations

from mcp.server.mcpserver.exceptions import ToolError

from postgres_mcp.application.ports import ExecutorPort
from postgres_mcp.domain.classifier import classify
from postgres_mcp.domain.config import PostgresConfig


def handle_execute_sql(
    sql: str, config: PostgresConfig, executor: ExecutorPort
) -> dict[str, object]:
    """Run one ``execute_sql`` call.

    Returns ``{"columns", "rows", "truncated", "row_count"}`` on success.
    Raises ``ToolError`` carrying the verbatim denial on classify-deny, or the
    ``"<sqlstate> <message>"`` PG-error envelope when the executor fails; the
    MCP server turns either into an ``isError`` result.
    """
    verdict = classify(sql, config.allow_writes)
    if not verdict.allowed:
        raise ToolError(verdict.denial)
    try:
        result = executor.execute(sql, read_only=not config.allow_writes)
    except Exception as exc:  # noqa: BLE001 - every executor failure is an error envelope
        code = getattr(exc, "sqlstate", None) or "?"
        raise ToolError(f"{code} {exc}") from exc
    return {
        "columns": list(result.columns),
        "rows": [tuple(row) for row in result.rows],
        "truncated": result.truncated,
        "row_count": result.row_count,
    }
