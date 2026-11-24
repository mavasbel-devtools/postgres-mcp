"""S-out implementation: one fresh psycopg connection per call (psycopg 3.3.9).

Cost is bounded twice: every new connection carries
``options='-c statement_timeout=<TIMEOUT_MS>'``, and the fetch stops at
``ROW_CAP + 1`` rows. Output is bounded once: at most ``ROW_CAP`` rows are
returned with the truncated flag set. The extended protocol
(``prepare=True`` with ``prepare_threshold = 0``) rejects stacked input at
Parse with ``42601`` so nothing in the stack runs. This module is the only
psycopg importer in the tree.
"""

from __future__ import annotations

from contextlib import suppress

import psycopg

from postgres_mcp.application.ports import ExecutorPort, QueryResult
from postgres_mcp.domain.config import PostgresConfig

TIMEOUT_MS = 15000
ROW_CAP = 500


class PsycopgExecutor(ExecutorPort):
    """The only ``ExecutorPort`` implementation. Construction does no I/O."""

    def __init__(self, config: PostgresConfig) -> None:
        self._config = config

    def execute(self, sql: str, read_only: bool) -> QueryResult:
        """Run one allowed statement on a fresh connection; close on every path."""
        conn = psycopg.connect(
            host=self._config.PG_HOST,
            port=self._config.PG_PORT,
            dbname=self._config.PG_DBNAME,
            user=self._config.PG_USER,
            password=self._config.PG_PASSWORD,
            options=f"-c statement_timeout={TIMEOUT_MS}",
        )
        try:
            if read_only:
                conn.read_only = True
            else:
                conn.autocommit = True
            conn.prepare_threshold = 0
            with conn.cursor() as cur:
                cur.execute(sql, prepare=True)
                if cur.description is None:
                    return QueryResult(
                        columns=(),
                        rows=(),
                        truncated=False,
                        row_count=max(cur.rowcount, 0),
                    )
                fetched = cur.fetchmany(ROW_CAP + 1)
                rows = fetched[:ROW_CAP]
                return QueryResult(
                    columns=tuple(col[0] for col in cur.description),
                    rows=tuple(tuple(row) for row in rows),
                    truncated=len(fetched) > ROW_CAP,
                    row_count=len(rows),
                )
        finally:
            if read_only:
                with suppress(Exception):
                    conn.rollback()
            conn.close()
