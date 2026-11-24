# postgres-mcp — product tree

Repo-relative companion to `AGENTS.md`. This document fixes the product
decomposition (purpose → features → use cases → components → data/states),
the verbatim denial texts, and the scenario ids that step 2.3 will realise
as `.feature` files. Machine-local absolute paths never appear below;
`{mwt}` means the `feat-postgres-mcp-v1` worktree.

Spike basis: brief-1.4 verdict (pglast 8.9 `parse_sql`, psycopg 3.3.9,
`spike_ro` on PG 18.6, `opencode mcp list`). All classifier rules below
trace to it.

## 0. Root

### N0 postgres-mcp server

- Purpose: expose PostgreSQL reads (and opt-in writes) to MCP clients
  through one stdio tool whose safety is enforced by code, never by the model.
- Contract — inputs: `execute_sql` calls carrying one SQL string; outputs:
  a result set or an error envelope; failure modes: DB unreachable, auth
  failure, timeout, truncation, parse error, malformed env value (each owned
  by the use case named in §6).
- Acceptance: all features F-read, F-gate, F-config, F-role green; scenario
  index §7 fully realised (`uc-read-ok-pos`, `uc-read-ok-neg`).
- Observable: `execute_sql("SELECT 1")` returns rows `[(1,)]`.

## 1. Features

### F-read — read path

- Purpose: serve read-only SQL with bounded cost and bounded output.
- Contract — inputs: one classified-allowed statement; outputs: columns,
  rows, truncated flag, row count; failure modes: DB unreachable, timeout,
  truncation.
- Acceptance: `uc-read-ok-pos`, `uc-read-ok-neg`, `uc-read-catalog-pos`,
  `uc-read-catalog-neg`, `uc-read-capped-pos`, `uc-read-capped-neg`,
  `uc-read-timeout-pos`, `uc-read-timeout-neg`.
- Observable: read use cases return data or PG error codes, never denials.

### F-gate — write gate (closed by default)

- Purpose: deny every non-read statement and every dangerous function while
  `PG_ALLOW_WRITES` is not exactly `1`; the classifier (not the transaction)
  is the real guard, because `SET TRANSACTION READ WRITE` succeeds inside
  `BEGIN READ ONLY` (spike row 8).
- Contract — inputs: `(sql, allow_writes)`; outputs: allow verdict or a
  verbatim denial from §5; failure modes: parse error, smuggled writes
  (CTE-hidden `DeleteStmt`, `intoClause`, `lockingClause`,
  `options`-carrying `EXPLAIN`), stacked statements (`n_stmts=2`).
- Acceptance: `uc-write-denied-default-pos`, `uc-write-denied-default-neg`,
  `uc-write-smuggled-pos`, `uc-write-smuggled-neg`,
  `uc-dangerous-function-pos`, `uc-dangerous-function-neg`,
  `uc-write-allowed-when-open-pos`, `uc-write-allowed-when-open-neg`,
  `uc-single-statement-pos`, `uc-single-statement-neg`.
- Observable: denied writes return `rejected: InsertStmt is not allowed while PG_ALLOW_WRITES is closed`.

### F-config — environment configuration

- Purpose: configure the server from the environment only; credentials are
  never tool parameters.
- Contract — inputs: `PG_HOST`, `PG_PORT`, `PG_USER`, `PG_PASSWORD`,
  optional `PG_DBNAME`, `PG_ALLOW_WRITES` (opens writes only when exactly
  `1`); outputs: a live connection or a fixed config error; failure modes:
  malformed env value, auth failure, DB unreachable.
- Acceptance: `uc-config-env-pos`, `uc-config-env-neg`.
- Observable: bad config returns `invalid PG_PORT 'abc': must be 1-65535`.

### F-role — database role layer

- Purpose: make a revoked read-only role the final enforcement layer, since
  read-only transactions alone are insufficient (spike rows 3/5/7 succeed
  inside one) while `GRANT`/`REVOKE` did the real enforcement (rows 1/2/8).
- Contract — inputs: `sql/create_readonly_role.sql` plus grant/revoke
  scripts; outputs: a least-privilege role; failure modes: auth failure
  (`28P01`), permission denial (`42501`).
- Acceptance: `uc-role-readonly-pos`, `uc-role-readonly-neg`,
  `uc-role-grant-revoke-pos`, `uc-role-grant-revoke-neg`.
- Observable: revoked INSERT returns `42501 permission denied for table cuenta_p07`.

## 2. Use cases

### read

#### UC-read-ok (`uc-read-ok`)

- Purpose: run a plain `SELECT` (covering `TABLE`/`VALUES`, which parse to
  plain `SelectStmt` with only `fromClause`/`valuesLists` set) and return rows.
- Contract — inputs: `SELECT 1`; outputs: `[(1,)]`; failure modes:
  DB unreachable.
- Acceptance: `uc-read-ok-pos` (returns `[(1,)]`); `uc-read-ok-neg`
  (unreachable host → connection error, nothing runs).
- Observable: `uc-read-ok-pos` yields `columns=[?column?], rows=[(1,)]`.

#### UC-read-catalog (`uc-read-catalog`)

- Purpose: answer schema questions from `information_schema` with reads only.
- Contract — inputs: catalog `SELECT`; outputs: catalog rows; failure modes:
  parse error on malformed SQL.
- Acceptance: `uc-read-catalog-pos` (catalog rows returned);
  `uc-read-catalog-neg` (garbage SQL → parse-error text).
- Observable: `uc-read-catalog-neg` yields `rejected: could not parse SQL: syntax error`.

#### UC-read-capped (`uc-read-capped`)

- Purpose: bound every result to the row-cap constant, flagging truncation.
- Contract — inputs: any allowed `SELECT`; outputs: at most row-cap rows
  plus `truncated`; failure modes: truncation (signalled, never silent).
- Acceptance: `uc-read-capped-pos` (over-cap query → `truncated=true`);
  `uc-read-capped-neg` (comment-smuggled cap bypass still `truncated=true`).
- Observable: `uc-read-capped-pos` yields `truncated=true with row-cap rows`.

#### UC-read-timeout (`uc-read-timeout`)

- Purpose: bound every call with the statement-timeout constant (`pg_sleep`
  cannot be the vehicle: it is deny-listed; use a slow but allowed `SELECT`).
- Contract — inputs: allowed `SELECT`; outputs: rows within budget or
  `57014`; failure modes: timeout.
- Acceptance: `uc-read-timeout-pos` (fast query returns rows);
  `uc-read-timeout-neg` (slow query aborted → timeout error).
- Observable: `uc-read-timeout-neg` yields `57014 canceling statement due to statement timeout`.

### gate

#### UC-write-denied-default (`uc-write-denied-default`)

- Purpose: deny writes out of the box (`PG_ALLOW_WRITES` unset or anything
  but exactly `1`).
- Contract — inputs: `INSERT`/`UPDATE`/`DELETE` with gate closed; outputs:
  verbatim denial; failure modes: none beyond the denial itself.
- Acceptance: `uc-write-denied-default-pos` (plain `INSERT` denied);
  `uc-write-denied-default-neg` (comment-obfuscated `INSERT` still denied).
- Observable: `uc-write-denied-default-pos` yields `rejected: InsertStmt is not allowed while PG_ALLOW_WRITES is closed`.

#### UC-write-smuggled (`uc-write-smuggled`)

- Purpose: catch writes hidden inside read-shaped syntax: CTEs hiding
  `DeleteStmt` (`withClause.ctes[0].ctequery=DeleteStmt`), `SELECT INTO`
  (`intoClause=IntoClause`), `FOR UPDATE` (`lockingClause`), `EXPLAIN
  ANALYZE` (`options=[DefElem 'analyze']`), plus `COPY PROGRAM`, `CALL`,
  `MERGE`, `DO` write paths.
- Contract — inputs: smuggled-write SQL, gate closed; outputs: verbatim
  denial naming the offending node; failure modes: none beyond denial.
- Acceptance: `uc-write-smuggled-pos` (`WITH x AS (DELETE …) SELECT …`
  denied); `uc-write-smuggled-neg` (`SELECT * INTO n FROM t` denied).
- Observable: `uc-write-smuggled-pos` yields `rejected: DeleteStmt is not allowed while PG_ALLOW_WRITES is closed`.

#### UC-dangerous-function (`uc-dangerous-function`)

- Purpose: deny dangerous functions anywhere in the tree (walk both
  `fromClause[*].functions[*][0]` pairs and `targetList[*].val`, lowercase
  compare): `set_config`, `pg_sleep`, `pg_terminate_backend` (+
  `pg_signal_backend` family), `pg_read_file`, `pg_ls_dir`, `lo_creat`,
  sequence `nextval` — all of which succeed or escape under read-only
  transactions except where GRANTs stop them.
- Contract — inputs: `SELECT` calling a listed function; outputs: verbatim
  function denial; failure modes: none beyond denial.
- Acceptance: `uc-dangerous-function-pos` (`SELECT set_config(…)` denied);
  `uc-dangerous-function-neg` (`SELECT pg_sleep(0.1)` denied).
- Observable: `uc-dangerous-function-pos` yields `rejected: function set_config is not allowed while PG_ALLOW_WRITES is closed`.

#### UC-write-allowed-when-open (`uc-write-allowed-when-open`)

- Purpose: permit genuine writes only when `PG_ALLOW_WRITES` is exactly `1`;
  the function denylist stays enforced in both gates (defence in depth).
- Contract — inputs: write SQL with gate open; outputs: applied write or
  function denial; failure modes: permission denial when the role lacks grants.
- Acceptance: `uc-write-allowed-when-open-pos` (`INSERT` applied);
  `uc-write-allowed-when-open-neg` (`pg_terminate_backend` still denied).
- Observable: `uc-write-allowed-when-open-pos` yields `applied INSERT with row count 1`.

#### UC-single-statement (`uc-single-statement`)

- Purpose: enforce exactly one statement per call (`n_stmts == 1` at the
  classifier; psycopg extended-protocol `execute` double-enforces with
  `42601 cannot insert multiple commands into a prepared statement`, but
  other protocols would run the stack, so the classifier owns this).
- Contract — inputs: any SQL string; outputs: pass-through or
  multi-statement denial; failure modes: parse error, `42601`.
- Acceptance: `uc-single-statement-pos` (single `SELECT` passes);
  `uc-single-statement-neg` (`SELECT 1; SELECT 2` denied, `n_stmts=2`).
- Observable: `uc-single-statement-neg` yields `rejected: exactly one statement is required, got 2`.

### config

#### UC-config-env (`uc-config-env`)

- Purpose: load all configuration from the environment and fail loudly on
  malformed values; any `PG_ALLOW_WRITES` value other than exactly `1`
  means closed (never an error).
- Contract — inputs: process env; outputs: connection parameters or fixed
  config error; failure modes: malformed env value, auth failure, DB
  unreachable.
- Acceptance: `uc-config-env-pos` (valid env connects);
  `uc-config-env-neg` (malformed value → config error).
- Observable: `uc-config-env-neg` yields `invalid PG_PORT 'abc': must be 1-65535`.

### role

#### UC-role-readonly (`uc-role-readonly`)

- Purpose: serve reads as the revoked role; the role (not the transaction)
  is what stops writes (`INSERT` → `42501` per spike row 8).
- Contract — inputs: role credentials; outputs: rows for reads, `42501`
  for writes; failure modes: auth failure (`28P01`).
- Acceptance: `uc-role-readonly-pos` (`SELECT` returns rows and `INSERT`
  → `42501`); `uc-role-readonly-neg` (wrong password → auth error).
- Observable: `uc-role-readonly-neg` yields `28P01 password authentication failed for user readonly_mcp`.

#### UC-role-grant-revoke (`uc-role-grant-revoke`)

- Purpose: exercise write paths by granting, then close them by revoking;
  temporary roles are always dropped and live tests touch only the
  `postgres` database.
- Contract — inputs: grant/revoke scripts + write SQL; outputs: applied
  write, then `42501`; failure modes: leaked grant (revoke must be verified).
- Acceptance: `uc-role-grant-revoke-pos` (granted `INSERT` applied);
  `uc-role-grant-revoke-neg` (post-revoke `INSERT` → `42501`).
- Observable: `uc-role-grant-revoke-neg` yields `42501 permission denied for table cuenta_p07`.

## 3. Components

### C-classifier — pure domain function `classify(sql, allow_writes)`

- Purpose: allowlist exactly one bare `SelectStmt` (or option-less
  `EXPLAIN` over one) when closed; reject `intoClause`, `lockingClause`,
  non-`SelectStmt` CTE bodies (recursively), all `SET`/`SET TRANSACTION`
  (`VariableSetStmt` wholesale, kinds 0 and 3), `TransactionStmt`,
  `DoStmt`, program-`CopyStmt`, `CallStmt`, `MergeStmt`, stacked statements,
  and every denylisted `FuncCall`. Imports nothing outside the domain.
- Contract — inputs: `(sql: str, allow_writes: bool)`; outputs: allow
  verdict or §5 denial; failure modes: parse error, smuggled write,
  stacked statements.
- Acceptance: component scenarios for `uc-write-denied-default-pos`,
  `uc-write-smuggled-pos`, `uc-write-smuggled-neg`,
  `uc-dangerous-function-pos`, `uc-dangerous-function-neg`,
  `uc-single-statement-pos`, `uc-single-statement-neg`,
  `uc-write-allowed-when-open-neg`; live suite per dependency is N/A (pure,
  no dependency).
- KISS: a single pure function over `pglast.parse_sql` — no rule engine,
  no visitor framework, no configuration; the allowlist shape (one node
  type plus field checks) is the whole design, and anything simpler
  (string matching, transaction-only) is refuted by the spike.
- Observable: `classify("WITH x AS (DELETE FROM t RETURNING *) SELECT * FROM x", False)` yields `rejected: DeleteStmt is not allowed while PG_ALLOW_WRITES is closed`.

### C-executor — outbound Postgres port

- Purpose: run one allowed statement per fresh connection: set statement
  timeout, use a read-only transaction when closed, fetch at most row-cap+1
  rows with the truncated flag, roll back when closed, close the connection.
- Contract — inputs: allowed SQL + gate state; outputs: §4 result set or
  PG error (`08001`/`08006`, `28P01`, `42501`, `57014`, `42601`, `25006`);
  failure modes: DB unreachable, auth failure, timeout, truncation.
- Acceptance: component scenarios (fakes) plus live suites for
  `uc-read-ok-pos`, `uc-read-ok-neg`, `uc-read-capped-pos`,
  `uc-read-timeout-pos`, `uc-read-timeout-neg`,
  `uc-write-allowed-when-open-pos`, `uc-role-readonly-pos`,
  `uc-role-grant-revoke-pos`, `uc-role-grant-revoke-neg`.
- KISS: one straight-line function (connect → set timeout → begin → run →
  fetch cap+1 → rollback-if-closed → close) with named constants, no pool,
  no retry, no ORM; pooling/retry would add failure modes no use case needs.
- Observable: over-cap fetch yields `row-cap rows with truncated=true`.

### C-config — environment loader

- Purpose: read `PG_HOST`/`PG_PORT`/`PG_USER`/`PG_PASSWORD`/`PG_DBNAME`/
  `PG_ALLOW_WRITES` from the environment, validate strictly, default closed.
- Contract — inputs: process env; outputs: typed parameters or fixed
  config error; failure modes: malformed env value (bad port, missing host).
- Acceptance: component scenarios for `uc-config-env-pos`,
  `uc-config-env-neg`; no live suite (no DB dependency).
- KISS: one `dataclass` plus one `load()` with inline range checks; no
  schema library, no file parsing, no defaults beyond `PG_DBNAME`; a
  validation dependency would outweigh three range checks.
- Observable: `load()` with `PG_PORT=abc` yields `invalid PG_PORT 'abc': must be 1-65535`.

### C-stdio-adapter — inbound MCP adapter (only MCP SDK importer)

- Purpose: expose exactly one tool, `execute_sql`, over stdio; classify,
  then execute, then render the result set or the error envelope; the tool
  description warns results are untrusted data.
- Contract — inputs: `execute_sql(sql)` calls; outputs: result/error JSON
  with `isError` on failures; failure modes: parse error, denial, PG error
  passthrough.
- Acceptance: component scenarios for `uc-read-ok-pos`,
  `uc-write-denied-default-pos`, `uc-single-statement-neg`; e2e covers the
  stack at the end.
- KISS: one thin handler delegating to classifier + executor port; no
  middleware, no session state, no second tool; any more surface would widen
  the attack perimeter without a use case.
- Observable: `execute_sql("DROP TABLE t")` yields `isError=true with rejected: DropStmt is not allowed while PG_ALLOW_WRITES is closed`.

### C-role-scripts — SQL role layer (`sql/`)

- Purpose: create the revoked read-only role idempotently (`DO`-guarded),
  with paired grant/revoke scripts for write exercises; psql variables only.
- Contract — inputs: psql invocation with variables; outputs: role with
  `CONNECT` + `USAGE` + `SELECT`-only grants and revoked signal/write
  functions; failure modes: auth failure, leaked grant.
- Acceptance: live scenarios for `uc-role-readonly-pos`,
  `uc-role-readonly-neg`, `uc-role-grant-revoke-pos`,
  `uc-role-grant-revoke-neg`.
- KISS: plain idempotent SQL scripts, no migration framework, no
  templating; three scripts are the whole layer and a framework would hide
  the exact grants under test.
- Observable: post-revoke `INSERT` yields `42501 permission denied for table cuenta_p07`.

## 4. Data and states

### D-result-set

- Purpose: the single read-result shape clients parse.
- Contract — inputs: cursor rows; outputs: `{columns, rows, truncated,
  row_count}`; failure modes: truncation (flagged via `truncated=true`).
- Acceptance: asserted by `uc-read-ok-pos`, `uc-read-capped-pos`.
- Observable: capped read yields `{columns, rows=row-cap, truncated=true, row_count=row-cap}`.

### D-error-envelope

- Purpose: the single failure shape: denials verbatim from §5, PG errors as
  code plus message, config errors as fixed text, always with `isError`.
- Contract — inputs: denial text or PG error; outputs: `{isError: true,
  text}`; failure modes: none (it is the failure carrier).
- Acceptance: asserted by every `*-neg` scenario and all denial scenarios.
- Observable: denied write yields `{isError: true, text: 'rejected: InsertStmt is not allowed while PG_ALLOW_WRITES is closed'}`.

### S-gate-closed (default)

- Purpose: the default state: only reads pass; every other node type and
  every denylisted function is rejected; `PG_ALLOW_WRITES` anything but
  exactly `1` lands here.
- Contract — inputs: `PG_ALLOW_WRITES != "1"`; outputs: closed-gate
  classifier behaviour; failure modes: none (fail-safe).
- Acceptance: `uc-write-denied-default-pos`, `uc-write-smuggled-pos`,
  `uc-dangerous-function-pos`, `uc-single-statement-neg`.
- Observable: closed-gate `INSERT` yields `rejected: InsertStmt is not allowed while PG_ALLOW_WRITES is closed`.

### S-gate-open (`PG_ALLOW_WRITES=1`)

- Purpose: the explicit opt-in state for write exercises; statement types
  open up, the function denylist stays on.
- Contract — inputs: `PG_ALLOW_WRITES == "1"`; outputs: open-gate
  classifier behaviour; failure modes: role `42501` still applies.
- Acceptance: `uc-write-allowed-when-open-pos`,
  `uc-write-allowed-when-open-neg`.
- Observable: open-gate `INSERT` yields `applied INSERT with row count 1`.

## 5. Denial texts (verbatim, exhaustive)

Closed-gate denials follow one template:

`rejected: <NodeType> is not allowed while PG_ALLOW_WRITES is closed`

with `<NodeType>` ∈ `InsertStmt`, `UpdateStmt`, `DeleteStmt`,
`MergeStmt`, `CopyStmt`, `CallStmt`, `DoStmt`, `TransactionStmt`,
`VariableSetStmt` (covers all `SET`, incl. `SET TRANSACTION`), `DropStmt`,
`CreateStmt`, `AlterStmt`, `GrantStmt`, `IntoClause`, `LockingClause`,
`ExplainStmt with options`, any other non-`SelectStmt` top node. Function
denials:

`rejected: function <name> is not allowed while PG_ALLOW_WRITES is closed`

with `<name>` ∈ `set_config`, `pg_sleep`, `pg_terminate_backend`,
`pg_signal_backend`, `pg_read_file`, `pg_ls_dir`, `lo_creat`, `nextval`
(and sequence siblings). Structural denials:

- `rejected: exactly one statement is required, got <n>`
- `rejected: could not parse SQL: <detail>`

Config errors (not denials): `missing required variable: <NAME>`,
`invalid PG_PORT '<value>': must be 1-65535`. PG passthroughs keep
`sqlstate + message` (`08001`, `08006`, `28P01`, `42501`, `25006`,
`42601`, `57014`).

## 6. Failure-mode → use-case matrix

| Failure mode | Primary use case | Observable text |
|---|---|---|
| DB unreachable | `uc-read-ok-neg` | `08001 connection error` |
| auth failure | `uc-role-readonly-neg` | `28P01 password authentication failed for user readonly_mcp` |
| timeout | `uc-read-timeout-neg` | `57014 canceling statement due to statement timeout` |
| truncation | `uc-read-capped-pos` | `truncated=true with row-cap rows` |
| parse error | `uc-read-catalog-neg` | `rejected: could not parse SQL: syntax error` |
| malformed env value | `uc-config-env-neg` | `invalid PG_PORT 'abc': must be 1-65535` |

## 7. Scenario index (component + live per use case)

Each use case owns one positive and one negative scenario, each run in its
component suite (fakes) and its live suite (real PG18 `postgres` database):

`uc-read-ok-pos`, `uc-read-ok-neg`, `uc-read-catalog-pos`,
`uc-read-catalog-neg`, `uc-read-capped-pos`, `uc-read-capped-neg`,
`uc-read-timeout-pos`, `uc-read-timeout-neg`,
`uc-write-denied-default-pos`, `uc-write-denied-default-neg`,
`uc-write-smuggled-pos`, `uc-write-smuggled-neg`,
`uc-dangerous-function-pos`, `uc-dangerous-function-neg`,
`uc-write-allowed-when-open-pos`, `uc-write-allowed-when-open-neg`,
`uc-single-statement-pos`, `uc-single-statement-neg`, `uc-config-env-pos`,
`uc-config-env-neg`, `uc-role-readonly-pos`, `uc-role-readonly-neg`,
`uc-role-grant-revoke-pos`, `uc-role-grant-revoke-neg`.

No use case was cut: every one of the 12 has directly observable behaviour
(a returned row set, a verbatim denial, or a PG/config error text).
