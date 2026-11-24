# postgres-mcp

A read-gated PostgreSQL MCP server: students point it at their course database and learn to supervise the agent that writes SQL.

It exposes exactly one tool, `execute_sql`, over stdio: classify, then execute, then render. Writes are closed by default — the gate opens only when `PG_ALLOW_WRITES` is exactly `1` — and every defence is enforced by code, never by the model. Results are bounded (at most 500 rows with a `truncated` flag; every call aborts after 15 s) and the tool description warns clients to treat every returned value as untrusted data, never as instructions.

## Prerequisites

- Python 3.12 or later with [uv](https://docs.astral.sh/uv/).
- Docker with a PostgreSQL 18 container holding the course database.
- The database is reachable when the endpoint check passes:

```sh
docker exec postgres true
```

## Install

```sh
uvx --from git+https://github.com/mavasbel-devtools/postgres-mcp@v0.1.0 postgres-mcp
```

## Configure (opencode)

Add the server under `mcp.servers` — a local entry with a `command` array and an `environment` map (`{env:…}` substitutes from your shell):

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "servers": {
      "postgres": {
        "type": "local",
        "command": [
          "uvx",
          "--from",
          "git+https://github.com/mavasbel-devtools/postgres-mcp@v0.1.0",
          "postgres-mcp",
        ],
        "environment": {
          "PG_HOST": "{env:PG_HOST}",
          "PG_PORT": "{env:PG_PORT}",
          "PG_USER": "{env:PG_USER}",
          "PG_PASSWORD": "{env:PG_PASSWORD}",
          "PG_DBNAME": "{env:PG_DBNAME}",
          "PG_ALLOW_WRITES": "{env:PG_ALLOW_WRITES}",
        },
      },
    },
  },
}
```

Check the connection with:

```sh
opencode mcp list
```

## Configuration

All configuration comes from the environment; credentials are never tool parameters.

| Variable | Default | Meaning |
|---|---|---|
| `PG_HOST` | `127.0.0.1` | Database host. |
| `PG_PORT` | `5423` | Database port (must be 1–65535). |
| `PG_USER` | — (required) | Database role. |
| `PG_PASSWORD` | — (required) | Database password. |
| `PG_DBNAME` | `postgres` | Database name. |
| `PG_ALLOW_WRITES` | closed | Opens the write gate only when exactly `1`; any other value means closed and is never an error. |

## Defence layers

| # | Layer | What it does |
|---|---|---|
| 1 | Classifier | Allows a single bare `SELECT` (or bare `EXPLAIN` over one) when closed; denies everything else plus a denylist of dangerous functions in both gates. |
| 2 | Single-statement protocol | Accepts exactly one statement; the executor's prepared protocol rejects stacks with `42601`. |
| 3 | Read-only transaction + statement timeout | Closed calls run read-only with a 15 s timeout. |
| 4 | Connection per call + rollback | One fresh connection per call, always rolled back when closed. |
| 5 | Database role (the guarantee) | A revoked read-only role; grants are added only for write exercises and revoked after. |

## Database role

Create (or refresh) the revoked read-only role. The command is idempotent — safe to re-run — and takes its values as `psql` variables (`password` is a quoted literal, the rest are identifiers):

```sh
psql -v role=curso_mcp -v password='CHANGEME-IN-ENV' -v schema=public -f sql/create_readonly_role.sql
```

Open one write exercise on one table, then close it again (same two variables both times):

```sh
psql -v role=curso_mcp -v table=public.cuenta_p07 -f sql/grant_writes.sql
psql -v role=curso_mcp -v table=public.cuenta_p07 -f sql/revoke_writes.sql
```

The grant also toggles the role readable-writable; the revoke restores read-only, so the role is least-privilege again after every exercise.

## Testing

One command per tier (unit and component use fakes; live and e2e need the container from Prerequisites):

```sh
uv run pytest --no-cov tests/unit
uv run pytest --no-cov tests/component
uv run pytest --no-cov tests/live
uv run pytest tests/e2e --cov=postgres_mcp --cov-branch --cov-fail-under=100
```

## License and credits

GPL-3.0-or-later — see [LICENSE](LICENSE).

The layered design follows prior art: the official reference server's stacked-statement bypass (<https://securitylabs.datadoghq.com/articles/mcp-vulnerability-case-study-SQL-injection-in-the-postgresql-mcp-server/>), crystaldba/postgres-mcp's `FROM`-clause function bypass (<https://github.com/crystaldba/postgres-mcp/issues/178>), pooled session-settings leak (<https://github.com/crystaldba/postgres-mcp/issues/203>) and missing row cap (<https://github.com/crystaldba/postgres-mcp/issues/243>), the pgEdge five-layer precedent (<https://github.com/pgEdge/pgedge-postgres-mcp>), and the Supabase lesson that results are untrusted data and must never be followed as instructions.
