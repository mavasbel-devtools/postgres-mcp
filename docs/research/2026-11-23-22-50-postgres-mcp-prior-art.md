# Postgres MCP prior art — 6-server survey

Survey date: 2026-11-23. Scope: six existing Postgres MCP servers, reviewed
before designing `postgres-mcp`. This note records the findings carried in
the plan's Why section, with all URLs. It is a research note: every claim
below is carried evidence for the architecture tree, and every defence it
motivates is measured again by the step-1.4 spike before any design is
written.

## 1. Official reference server — stacked-statement bypass

The official Postgres reference MCP server was bypassed with stacked input
such as `COMMIT; DROP SCHEMA public CASCADE;`. A single read-only defence
does not hold against a second statement riding along. Reported by Datadog
Security Labs:

- <https://securitylabs.datadoghq.com/articles/mcp-vulnerability-case-study-SQL-injection-in-the-postgresql-mcp-server/>

Lesson carried into the design: the classifier must accept exactly one
statement, and the executor must enforce the single-statement protocol —
never trust one layer alone.

## 2. crystaldba/postgres-mcp — pglast bypass via function in FROM (#178)

crystaldba's pglast-based check was bypassed by hiding a dangerous function
inside a `FROM` clause, e.g. `SELECT * FROM pg_read_file('/etc/passwd')`.
The function walk missed `RangeFunction` nodes:

- <https://github.com/crystaldba/postgres-mcp/issues/178>

Lesson carried into the design: every `FuncCall` anywhere in the parsed
tree — including inside `RangeFunction` and in the target list — must be
checked against the denylist, by unqualified and `pg_catalog.`-qualified
name.

## 3. crystaldba/postgres-mcp — session-settings leak across pooled connections (#203)

crystaldba leaks session settings across pooled connections:

- <https://github.com/crystaldba/postgres-mcp/issues/203>

Lesson carried into the design: one new connection per call, and always
`ROLLBACK` when the gate is closed, so no session state survives a call.

## 4. crystaldba/postgres-mcp — no row cap (#243)

crystaldba has no row cap, so a single query can flood the model context:

- <https://github.com/crystaldba/postgres-mcp/issues/243>

Lesson carried into the design: fetch at most row-cap + 1 rows and set a
truncated flag. The row cap is a named constant, not configuration.

## 5. pgEdge — layered design

pgEdge layers a text guard, a read-only transaction, a read-only session
default and a revoked role:

- <https://github.com/pgEdge/pgedge-postgres-mcp>

Lesson carried into the design: the five defence layers (classifier,
single-statement protocol, read-only transaction plus statement timeout,
connection per call plus `ROLLBACK`, the database role as the guarantee)
follow this layered precedent, with the role as the final guarantee.

## Verdict for the design

A single read-only defence fails, as the bypasses above show. The design
therefore layers all five defences, with the database role as the final
layer. Open measurements (pglast 8.9 node names, psycopg 3.3.9 protocol
behaviour, PG18 function behaviour under a read-only role) belong to the
step-1.4 spike, not to this note.
