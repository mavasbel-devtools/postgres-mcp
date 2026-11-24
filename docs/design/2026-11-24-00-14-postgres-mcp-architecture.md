# postgres-mcp — architecture tree

Repo-relative companion to `AGENTS.md`. This document fixes the code
decomposition (package → modules → classes/functions → methods), the code
names stage 3 will use verbatim, and the two seams. Machine-local absolute
paths never appear below; `{mwt}` means the `feat-postgres-mcp-v1`
worktree.

Plan binding: step 2.2 of
`2026-11-24-00-14-postgres-mcp-repo.md` (SHA-256 verified OK).
Sources read before writing: the sibling product tree
(`2026-11-24-00-14-postgres-mcp-product.md`), the brief-1.4 spike
verdicts (`brief-1.4/verdict.md`), and the prior-art note
(`docs/research/2026-11-23-22-50-postgres-mcp-prior-art.md`).
The `x-mcp` layout (`domain/`, `application/`, `infrastructure/adapters/`,
`main/`) is used below only as vocabulary where a seam exists; everything
else is flat inside the package. No other abstraction exists.

## 0. Seams (the only abstractions allowed)

There are exactly two seams, and exactly one interface in the whole design:

| # | Seam | Kind | Interface / implementation |
|---|---|---|---|
| S-in | Inbound: MCP stdio adapter | concrete only, no interface | `postgres_mcp/infrastructure/adapters/stdio.py` :: `handle_execute_sql` is the single MCP SDK importer; no port, no base class, no protocol on this side |
| S-out | Outbound: Postgres executor port | one abstract base class + one implementation | `postgres_mcp/application/ports.py` :: `ExecutorPort` (abstract) → `postgres_mcp/infrastructure/adapters/postgres.py` :: `PsycopgExecutor` (only implementation) |

Seam check (gate 1): the full interface/base-class inventory of this
design is: `ExecutorPort` — sits at S-out (outbound Postgres executor
port). No other `class …:`, `Protocol`, `ABC`, visitor, rule-engine, or
plugin base exists anywhere in the tree below. The stdio side (S-in) is a
concrete handler, not an abstraction. Any speculative abstraction found
later is removed under PROBLEMS, not documented.

## 1. Package tree

Package root: `postgres_mcp` (a single package; `sql/` scripts live beside
it at `{mwt}/sql/`, they are not Python).

```
postgres_mcp/
  domain/
    classifier.py      # pure gate: classify + Verdict + DENIED_FUNCTIONS
    config.py          # frozen env config: PostgresConfig + load_config
  application/
    ports.py           # S-out port: ExecutorPort + QueryResult
  infrastructure/
    adapters/
      postgres.py      # S-out implementation: PsycopgExecutor (+ TIMEOUT_MS, ROW_CAP)
      stdio.py         # S-in adapter: handle_execute_sql (only MCP SDK importer)
  main/
    server.py          # composition root: build_server + main
sql/
  create_readonly_role.sql
  grant_write.sql
  revoke_write.sql
```

`domain/` holds pure logic with no I/O imports. `application/ports.py`
exists only because S-out needs a port. `infrastructure/adapters/`
exists only because both seams need a home. `main/` exists only as the
single composition root. No other layer, factory, registry, or helper
module exists.

## 2. Nodes

### A0 `postgres_mcp` — package

- Product node: N0 postgres-mcp server.
- Responsibility: own every code name below and nothing else.
- Public interface: the module paths named in §1.
- Holding test directory: `tests/` (suites per node below).

### A1 `postgres_mcp/domain/classifier.py` — pure gate

- Product node: C-classifier.
- Responsibility: decide allow/deny for `(sql, allow_writes)` with zero I/O.
- Public interface: `classify(sql, allow_writes) -> Verdict`;
  `Verdict`; `DENIED_FUNCTIONS`.
- Holding test directory: `tests/component` (classifier suite; pure, so no
  `tests/live` suite — N/A per product tree) plus `tests/unit` for
  `Verdict` shape and denylist normalisation.
- Methods/functions:
  - `classify(sql: str, allow_writes: bool) -> Verdict` — the whole gate:
    `pglast.parse_sql` → `n_stmts == 1` check → closed/open branch below →
    `Verdict(allowed=True, …)` or `Verdict(allowed=False, denial, node)`.
    Parse failure yields
    `rejected: could not parse SQL: <detail>`.
  - `Verdict` — frozen dataclass, exact shape:
    `allowed: bool`, `denial: str` (empty when allowed; otherwise a verbatim
    §5 denial text), `node: str` (empty when allowed; otherwise the
    offending node type, e.g. `InsertStmt`, `DeleteStmt`, `IntoClause`,
    `LockingClause`, `ExplainStmt with options`, or the function name in
    `rejected: function <name> is not allowed …`).
  - `DENIED_FUNCTIONS: frozenset[str]` — lowercase unqualified names; every
    `FuncCall` anywhere in the tree, including inside `RangeFunction`
    (`fromClause[*].functions[*][0]` pairs) and `targetList[*].val`
    (`ResTarget.val`), is lowercased and compared by unqualified and
    `pg_catalog.`-qualified name.
  - Closed gate (`allow_writes is False`; anything but exactly `1` in
    `PG_ALLOW_WRITES` lands here via `load_config`): pass only when the
    single top node is a `SelectStmt` with no `intoClause`, no
    `lockingClause`, and every CTE body (`withClause.ctes[*].ctequery`,
    applied recursively through set ops and subqueries) is itself a
    `SelectStmt` passing the same test; or an `ExplainStmt` with no
    `analyze` option (no `options` at all) wrapping a statement passing the
    same test; `VALUES`/`TABLE` parse to `SelectStmt` (only
    `fromClause`/`valuesLists` set) and pass as plain selects. Function
    walk (both gates): every `FuncCall` anywhere, including inside
    `RangeFunction`, is checked against `DENIED_FUNCTIONS`
    (`pg_read_file`, `pg_read_binary_file`, `pg_ls_dir`, `pg_stat_file`,
    `set_config`, `pg_terminate_backend`, `pg_cancel_backend`,
    `pg_reload_conf`, `pg_rotate_logfile`, `dblink*`, `lo_*`, plus
    `pg_sleep`, `pg_signal_backend` and anything else the spike verdicts
    show succeeding); match by unqualified and `pg_catalog.`-qualified
    name. Every other top node type is denied as
    `rejected: <NodeType> is not allowed while PG_ALLOW_WRITES is closed`.
  - Open gate (`allow_writes is True`, i.e. `PG_ALLOW_WRITES` is exactly
    `1`): pass one statement of any type except `TransactionStmt`,
    `VariableSetStmt`, `DiscardStmt`, `DoStmt`, with the same
    `DENIED_FUNCTIONS` walk as the closed gate. The function denylist stays enforced in both gates (the open gate lifts only the statement-type allowlist). The role decides everything else.
  - Denial texts used here (verbatim from product-tree §5): template
    `rejected: <NodeType> is not allowed while PG_ALLOW_WRITES is closed`
    with `<NodeType>` ∈ `InsertStmt`, `UpdateStmt`, `DeleteStmt`,
    `MergeStmt`, `CopyStmt`, `CallStmt`, `DoStmt`, `TransactionStmt`,
    `VariableSetStmt`, `DropStmt`, `CreateStmt`, `AlterStmt`, `GrantStmt`,
    `IntoClause`, `LockingClause`, `ExplainStmt with options`, any other
    non-`SelectStmt` top node; function template
    `rejected: function <name> is not allowed while PG_ALLOW_WRITES is closed`;
    structural `rejected: exactly one statement is required, got <n>` and
    `rejected: could not parse SQL: <detail>`.

### A2 `postgres_mcp/domain/config.py` — environment loader

- Product node: C-config.
- Responsibility: read the six `PG_*` variables and fail loudly on malformed values.
- Public interface: `PostgresConfig`; `load_config`.
- Holding test directory: `tests/component` (env scenarios; no `tests/live`
  suite — no DB dependency).
- Methods/functions:
  - `PostgresConfig` — frozen dataclass with exactly six fields: `PG_HOST`
    (default `127.0.0.1`), `PG_PORT` (default `5423`, validated 1–65535),
    `PG_USER` (no default — required), `PG_PASSWORD` (no default —
    required), `PG_DBNAME` (default `postgres`), `PG_ALLOW_WRITES` (raw
    string kept; open only when exactly `1`, anything else means closed and
    is never an error). Row cap and timeout are NOT fields here — they are
    the constants `ROW_CAP` and `TIMEOUT_MS` in
    `postgres_mcp/infrastructure/adapters/postgres.py`.
  - `load_config(env) -> PostgresConfig` — one strict loader with inline
    range checks; malformed values yield the fixed config errors, e.g.
    `invalid PG_PORT 'abc': must be 1-65535`, and missing values yield
    `missing required variable: <NAME>`.

### A3 `postgres_mcp/application/ports.py` — S-out port (the one interface)

- Product node: C-executor (port side).
- Responsibility: define the single outbound seam the executor implements.
- Public interface: `ExecutorPort`; `QueryResult`.
- Holding test directory: `tests/component` (fake-executor suites).
- Methods/functions:
  - `ExecutorPort` — abstract base class (S-out seam); single abstract
    method `execute(self, sql: str, read_only: bool) -> QueryResult`.
    This is the only interface/base class in the design (see §0).
  - `QueryResult` — frozen dataclass: `columns: tuple[str, …]`,
    `rows: tuple[tuple, …]` (at most `ROW_CAP` entries),
    `truncated: bool`, `row_count: int`.

### A4 `postgres_mcp/infrastructure/adapters/postgres.py` — S-out implementation (psycopg 3.3.9)

- Product node: C-executor (implementation side).
- Responsibility: run one allowed statement per fresh connection with bounded cost and bounded output.
- Public interface: `PsycopgExecutor`; `TIMEOUT_MS`; `ROW_CAP`.
- Holding test directory: `tests/live` (real PG18 `postgres` database) plus
  `tests/component` (port-fake suites); `tests/e2e` quotes the constants.
- Methods/functions:
  - `PsycopgExecutor(ExecutorPort)` — the only port implementation; method
    `execute(self, sql: str, read_only: bool) -> QueryResult`.
  - Constants: `TIMEOUT_MS = 15000`, `ROW_CAP = 500` — fixed here, quoted
    by e2e tests and the operator guide; never configuration, never env.
  - Behaviour (exact): one new connection per call with
    `options='-c statement_timeout=<TIMEOUT_MS>'`; `conn.read_only = True`
    when closed; `cursor.execute(sql, prepare=True)` with
    `prepare_threshold = 0` (the path the spike proves enforces single
    statement: stacked input fails `42601 cannot insert multiple commands
    into a prepared statement` and nothing runs); fetch at most `ROW_CAP +
    1` rows, return at most `ROW_CAP` with `truncated` flag; always
    `ROLLBACK` when closed, autocommit for the one statement when open;
    close the connection on every path.

### A5 `postgres_mcp/infrastructure/adapters/stdio.py` — S-in adapter (only MCP SDK importer)

- Product node: C-stdio-adapter.
- Responsibility: expose exactly one tool, `execute_sql`, over stdio; classify, then execute, then render.
- Public interface: `handle_execute_sql`.
- Holding test directory: `tests/component` (handler scenarios with a fake
  `ExecutorPort`); `tests/e2e` covers the stack at the end.
- Methods/functions:
  - `handle_execute_sql(sql: str, config: PostgresConfig, executor: ExecutorPort)` —
    one thin handler: `load_config` state → `classify(sql,
    allow_writes)` → denial envelope on deny → `executor.execute(sql,
    read_only)` on allow → result-set dict or PG-error envelope
    (`08001`/`08006`, `28P01`, `42501`, `57014`, `42601`, `25006`
    passthrough with sqlstate + message); the tool description warns
    results are untrusted data. No middleware, no session state, no second
    tool.

### A6 `postgres_mcp/main/server.py` — composition root

- Product node: N0 (wiring only; no product behaviour of its own).
- Responsibility: wire config → classifier inputs → executor → stdio, once.
- Public interface: `build_server`; `main`.
- Holding test directory: `tests/e2e` (whole stack through the real
  composition root, final gate only).
- Methods/functions:
  - `build_server()` — `load_config(os.environ)` →
    `PsycopgExecutor(config)` → returns the bound `handle_execute_sql`
    closure. The single runtime injection point.
  - `main()` — run the stdio loop; argument-free.

### A7 `sql/` — role scripts (not Python, part of the tree)

- Product node: C-role-scripts.
- Responsibility: create the revoked read-only role idempotently with paired grant/revoke scripts for write exercises.
- Public interface: `sql/create_readonly_role.sql`;
  `sql/grant_write.sql`; `sql/revoke_write.sql` (psql variables only,
  `DO`-guarded idempotent role creation).
- Holding test directory: `tests/live` (grant/revoke scenarios against the
  `postgres` database only).

## 3. Defence layers (evidence)

| # | Layer | What it is in this tree | Evidence motivating it |
|---|---|---|---|
| 1 | Classifier | `classify` in `postgres_mcp/domain/classifier.py`: `SelectStmt`-only allowlist + `DENIED_FUNCTIONS` walk incl. `RangeFunction` | Prior art: crystaldba pglast bypass hid `pg_read_file` in `FROM` — "every `FuncCall` anywhere in the parsed tree — including inside `RangeFunction` … must be checked … by unqualified and `pg_catalog.`-qualified name" — <https://github.com/crystaldba/postgres-mcp/issues/178>; spike verdicts: "walk **both** `fromClause[*].functions[*][0]` and `targetList[*].val`, compare lowercase funcname against the denylist" and "allowlist must accept ONLY `SelectStmt` with `intoClause=None`, `lockingClause=None` …, `ExplainStmt` only with `options=None` …, and zero tolerance for `TransactionStmt`, `VariableSetStmt` …, `DoStmt`, `CopyStmt` with `is_program`, `CallStmt`, `MergeStmt`" (`brief-1.4/verdict.md` §1, rows 1–17) |
| 2 | Single-statement protocol | `n_stmts == 1` in `classify` plus `cursor.execute(sql, prepare=True)` with `prepare_threshold = 0` in `postgres_mcp/infrastructure/adapters/postgres.py` :: `PsycopgExecutor` | Prior art: official reference server bypassed with stacked `COMMIT; DROP SCHEMA public CASCADE;` — "the classifier must accept exactly one statement, and the executor must enforce the single-statement protocol — never trust one layer alone" — <https://securitylabs.datadoghq.com/articles/mcp-vulnerability-case-study-SQL-injection-in-the-postgresql-mcp-server/>; spike verdicts: "`cur.execute(\"SELECT 1; SELECT 2\", prepare=True)` → `psycopg.errors.SyntaxError`, sqlstate `42601`, `cannot insert multiple commands into a prepared statement` — nothing runs" but "the allowlist must still enforce `n_stmts == 1`, because other paths (simple-query protocol, `conn.execute`, future drivers) do run stacked statements" (`brief-1.4/verdict.md` §2) |
| 3 | Read-only transaction + statement timeout | `conn.read_only = True` when closed and `options='-c statement_timeout=<TIMEOUT_MS>'` (`TIMEOUT_MS = 15000`) in `PsycopgExecutor` | Prior art: pgEdge layers "a text guard, a read-only transaction, a read-only session default and a revoked role" — <https://github.com/pgEdge/pgedge-postgres-mcp>; spike verdicts: `SELECT pg_sleep(0.1)` "**SUCCESS** — holds a connection → **denylist `pg_sleep`** (slow-query DoS)" and `SET TRANSACTION READ WRITE` "**SUCCEEDS** … `BEGIN READ ONLY` is escapable before the first statement" (`brief-1.4/verdict.md` §3 rows 7–8) — the transaction alone is insufficient, the timeout bounds what it cannot stop |
| 4 | Connection per call + ROLLBACK | one new connection per `PsycopgExecutor.execute` call; always `ROLLBACK` when closed; close on every path | Prior art: crystaldba "leaks session settings across pooled connections" — "one new connection per call, and always `ROLLBACK` when the gate is closed, so no session state survives a call" — <https://github.com/crystaldba/postgres-mcp/issues/203>; and "no row cap, so a single query can flood the model context" — "fetch at most row-cap + 1 rows and set a truncated flag" — <https://github.com/crystaldba/postgres-mcp/issues/243>; spike verdicts: `SELECT set_config('statement_timeout','0',false)` "**SUCCESS** … GUC change allowed in read-only txn → **denylist `set_config` + all `SET`**" (`brief-1.4/verdict.md` §3 row 3) — per-call connections plus `ROLLBACK` contain exactly this class of session-state escape |
| 5 | Database role (the guarantee) | `sql/create_readonly_role.sql` (+ `sql/grant_write.sql` / `sql/revoke_write.sql`); `PostgresConfig` carries the role credentials, never tool parameters | Prior art: the five-layer precedent "with the role as the final guarantee" — <https://github.com/pgEdge/pgedge-postgres-mcp>; spike verdicts: "read-only txn alone is **insufficient** (row 8: `SET TRANSACTION` escapes it; rows 3/5/7 succeed inside it). The GRANT/REVOKE layer did the real enforcement (rows 1/2/8)" and "row 8 … SQL2 then fails `42501` permission denied for table (no INSERT grant)" (`brief-1.4/verdict.md` §3) |

## 4. Dependencies (each with justification and beaten alternative)

| Dependency | Used in | Justification | Beaten alternative |
|---|---|---|---|
| `mcp` (MCP Python SDK) | `postgres_mcp/infrastructure/adapters/stdio.py` only — the single SDK importer | Only way to expose `execute_sql` over stdio to MCP clients; confines all protocol surface to S-in | Raw JSON-RPC over stdio hand-rolled: wider untested surface, no use case needs it |
| `pglast` (8.9, `pglast.parse_sql`) | `postgres_mcp/domain/classifier.py` only | Only parser giving real node types (`SelectStmt`, `ExplainStmt`, `VariableSetStmt`, `DoStmt`, `CopyStmt`, `CallStmt`, `MergeStmt`, `FuncCall` in `RangeFunction`) the spike verified row by row; string matching is refuted by the CTE/`SELECT INTO`/`FOR UPDATE` smuggling rows | Regex/string allowlist: misses `withClause.ctes[0].ctequery=DeleteStmt`, `intoClause=IntoClause`, `lockingClause`, `options=[DefElem 'analyze']` — refuted by spike §1 rows 6–8 |
| `psycopg` (3.3.9) | `postgres_mcp/infrastructure/adapters/postgres.py` only | Only driver path the spike proves rejects stacked statements at Parse (`42601`) with `prepare=True` / `prepare_threshold = 0`, keeping single-statement enforcement double-layered | `psycopg2` / simple-query-protocol drivers: run stacked statements; connection pools: leak session settings per crystaldba #203 — both refuted by spike §2 and prior art |

No other third-party dependency exists. In particular: no validation
library (three range checks in `load_config`), no ORM, no pool, no retry,
no migration framework, no visitor/rule-engine framework.

## 5. Code names index (stage 3 uses these verbatim)

Module paths: `postgres_mcp/domain/classifier.py`,
`postgres_mcp/domain/config.py`, `postgres_mcp/application/ports.py`,
`postgres_mcp/infrastructure/adapters/postgres.py`,
`postgres_mcp/infrastructure/adapters/stdio.py`,
`postgres_mcp/main/server.py`, `sql/create_readonly_role.sql`,
`sql/grant_write.sql`, `sql/revoke_write.sql`.

Functions/classes/constants: `classify`, `Verdict`, `DENIED_FUNCTIONS`,
`PostgresConfig`, `load_config`, `ExecutorPort`, `QueryResult`,
`PsycopgExecutor`, `TIMEOUT_MS`, `ROW_CAP`, `handle_execute_sql`,
`build_server`, `main`, `execute`, `PG_HOST`, `PG_PORT`, `PG_USER`,
`PG_PASSWORD`, `PG_DBNAME`, `PG_ALLOW_WRITES`.

Test roots: `tests/unit`, `tests/component`, `tests/live`, `tests/e2e`.

## 6. Resolved conflict (user decision 2026-11-24)

The earlier draft followed the pre-amendment plan text: the open gate
passed any statement type except `TransactionStmt`, `VariableSetStmt`,
`DiscardStmt`, `DoStmt` with no function check, while the product tree
(UC `uc-write-allowed-when-open`) and
`tests/features/uc-write-allowed-when-open.feature` kept the function
denylist enforced in both gates. The user decided on 2026-11-24 that the
dangerous-function denylist stays enforced in BOTH gates — the open gate
lifts only the statement-type allowlist — and the plan was amended
accordingly (step 2.2 open-gate bullet now carries the both-gates rule;
step 3.3 timeout bullet is now classifier-bypassed). The A1 open gate
above implements the amended rule: the same `DENIED_FUNCTIONS` walk runs
in both gates. Product tree, feature file, and this document now agree;
no reconciliation remains for step 2.4 on this point.
