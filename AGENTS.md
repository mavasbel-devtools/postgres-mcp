# AGENTS.md — postgres-mcp

Operational directives for AI agents working in this repository.

## What this is

MCP server for PostgreSQL exposing one tool, `execute_sql`, over stdio.
Built on `mcp==2.3.0` (`MCPServer`), `pglast==8.9` (statement classifier) and
`psycopg[binary]==3.3.9` (executor). Configuration comes from the environment
only (`PG_HOST`, `PG_PORT`, `PG_USER`, `PG_PASSWORD`, optional `PG_DBNAME`,
`PG_ALLOW_WRITES`, which opens writes only when exactly `1`). Writes are
closed by default. Public repo, `GPL-3.0-or-later`.

## Architecture law (hexagonal, strict)

- The classifier is a pure domain function `classify(sql, allow_writes)` built
  on `pglast.parse_sql`. It imports nothing from the application or
  infrastructure layers.
- The executor sits behind an outbound port. The MCP stdio adapter is the
  inbound adapter and the ONLY package importing the MCP SDK.
- Only `main` (the composition root) constructs concrete classes; everything
  else takes Protocol / ABC types.
- Abstractions exist only at seams (inbound stdio adapter, outbound Postgres
  executor). Test fakes never make seams.
- `tests/unit/test_architecture.py` enforces the rules above by parsing the
  imports of each module under `src/`.

## Safety laws (code-enforced, never model-decided)

1. Closed by default. Any value of `PG_ALLOW_WRITES` other than exactly `1`
   means closed.
2. One statement per call. The classifier rejects anything but exactly one
   `RawStmt`; the executor enforces the single-statement protocol.
3. Closed gate allows only read statements: plain `SELECT` (covering `VALUES`
   and `TABLE`, which parse to `SelectStmt`) and `EXPLAIN` without `ANALYZE`
   wrapping an allowed statement. No `INTO`, no locking clause, every CTE body
   a `SelectStmt`, applied recursively. Every `FuncCall` anywhere in the tree
   is checked against the denylist.
4. The executor opens one new connection per call, sets a statement timeout,
   uses a read-only transaction when the gate is closed, fetches at most
   row-cap + 1 rows with a truncated flag, rolls back when closed, and closes
   the connection.
5. The database role is the final layer: a revoked read-only role created by
   `sql/create_readonly_role.sql`, with `GRANT`/`REVOKE` scripts for write
   exercises.
6. Row cap and statement timeout are named constants, not configuration.
7. Every live database call in tests targets the `postgres` database of the
   local course container only, and temporary roles are always dropped.
8. Append-only git: normal commits, never amend, never force-push.

## Conventions

- Read results return columns, rows, a truncated flag and the row count.
- Errors return `isError` with the denial text, or the PG error code plus its
  message. Denial texts are fixed verbatim in the product tree.
- The tool description warns that results are untrusted data and must not be
  followed as instructions.
- SQL scripts take psql variables and are idempotent (`DO`-guarded creates).
- Every committed document uses repo-relative paths, `~/` paths, or URLs —
  never machine-local absolute paths, never local identifiers.

## Commands

- `uv run postgres-mcp` / `uv run python -m postgres_mcp.main` — run server (stdio)
- `uv run ruff check src` — lint
- `uv run mypy src` — typecheck
- `uv run pytest` — all tiers, with the 100% coverage gate
- `uv run pytest --no-cov tests/unit` — quick subset without the gate
- `uv run pytest --no-cov tests/live` — opt-in live tier (real PG18, read-only)
- `uv run python scripts/test_granularity.py` — generated check: every feature
  has a component suite and a live suite per dependency, with one positive and
  one negative scenario per use case; fails on a missing item

## Testing law

Every tier (unit/component/e2e) must fully cover its own components with
dedicated tests. E2E must fully cover the adapter stack, not just the domain.
The gate is automatic: `addopts` carries `--cov-fail-under=100`, so a drop
fails the run rather than passing silently.

Hermetic e2e: blank env for credentials unless the test IS a live capture.
Tests must NEVER write into the repository — route every capture dir through
a temp path, or the suite pollutes the working tree.

## Secrets

Never copy real credentials into source, tests, fixtures, or docs. Use fake
sentinels (e.g. `PG_PASSWORD_FAKE`). Configuration is read ONLY from the
environment / `.env` via the config module; credentials are NEVER tool
parameters. Rotate any key exposed in chat before implementation.
