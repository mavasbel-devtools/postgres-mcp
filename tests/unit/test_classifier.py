"""Unit tests for postgres_mcp.domain.classifier (step 3.1).

Covers every scenario of uc-write-smuggled, uc-dangerous-function, and
uc-single-statement, plus the brief extras: lowercase/padded variants,
quoted identifiers named like keywords, string literals holding ``; DROP``,
nested set operations, EXPLAIN over a data-modifying CTE, empty input, and
parse errors carrying pglast's message. One test id per adversarial case.
"""

import dataclasses

import pytest

from postgres_mcp.domain.classifier import DENIED_FUNCTIONS, Verdict, classify

CLOSED = "is not allowed while PG_ALLOW_WRITES is closed"


def assert_statement_denial(sql, node, allow_writes=False):
    assert classify(sql, allow_writes) == Verdict(
        allowed=False, denial=f"rejected: {node} {CLOSED}", node=node
    )


def assert_function_denial(sql, name, allow_writes=False):
    assert classify(sql, allow_writes) == Verdict(
        allowed=False, denial=f"rejected: function {name} {CLOSED}", node=name
    )


# --- uc-single-statement: one statement passes ---------------------------------


@pytest.mark.parametrize(
    "sql",
    ["SELECT 1", "select 1", "  SELECT 1  \n"],
    ids=["single-select", "lowercase-select", "padded-select"],
)
def test_single_statement_passes(sql):
    assert classify(sql, False) == Verdict(allowed=True, denial="", node="")


@pytest.mark.parametrize(
    ("sql", "n"),
    [
        ("SELECT 1; SELECT 2", 2),
        ("SELECT 1; DELETE FROM t", 2),
        ("SELECT 1; SELECT 2; SELECT 3", 3),
        ("SELECT 1; SELECT 2 -- stacked read-smuggled stack", 2),
    ],
    ids=[
        "two-selects",
        "select-delete-stack",
        "three-selects",
        "stacked-reads-comment",
    ],
)
def test_stacked_statements_denied(sql, n):
    assert classify(sql, False) == Verdict(
        allowed=False,
        denial=f"rejected: exactly one statement is required, got {n}",
        node="",
    )


# --- uc-write-smuggled: hidden writes -------------------------------------------


@pytest.mark.parametrize(
    ("sql", "node"),
    [
        ("WITH x AS (DELETE FROM t RETURNING *) SELECT * FROM x", "DeleteStmt"),
        (
            "WITH x AS (INSERT INTO t VALUES (1) RETURNING *) SELECT * FROM x",
            "InsertStmt",
        ),
        ("WITH x AS (UPDATE t SET a = 1 RETURNING *) SELECT * FROM x", "UpdateStmt"),
        (
            "WITH x AS (DELETE /* hidden */ FROM t RETURNING *) SELECT * FROM x",
            "DeleteStmt",
        ),
        (
            "WITH x AS (WITH y AS (DELETE FROM t RETURNING *) SELECT * FROM y) SELECT * FROM x",
            "DeleteStmt",
        ),
        (
            "(WITH x AS (DELETE FROM t RETURNING *) SELECT * FROM x) UNION SELECT 1",
            "DeleteStmt",
        ),
        ("SELECT * INTO n FROM t", "IntoClause"),
        ("SELECT 'INTO' INTO n FROM t", "IntoClause"),
        ("SELECT * FROM t FOR UPDATE", "LockingClause"),
        ("SELECT * FROM t FOR UPDATE /* trailing */", "LockingClause"),
        ("EXPLAIN ANALYZE SELECT * FROM t", "ExplainStmt with options"),
        ("EXPLAIN /* comment */ ANALYZE SELECT * FROM t", "ExplainStmt with options"),
        ("EXPLAIN (COSTS OFF) SELECT 1", "ExplainStmt with options"),
        ("EXPLAIN DELETE FROM t", "DeleteStmt"),
        (
            "EXPLAIN WITH x AS (DELETE FROM t RETURNING *) SELECT * FROM x",
            "DeleteStmt",
        ),
    ],
    ids=[
        "cte-delete",
        "cte-insert",
        "cte-update",
        "cte-delete-comment",
        "cte-nested-delete",
        "cte-delete-in-setop-branch",
        "select-into",
        "select-into-string-literal",
        "for-update",
        "for-update-trailing-comment",
        "explain-analyze",
        "explain-comment-analyze",
        "explain-costs-off",
        "explain-delete",
        "explain-delete-cte",
    ],
)
def test_smuggled_write_denied(sql, node):
    assert_statement_denial(sql, node)


@pytest.mark.parametrize(
    ("sql", "node"),
    [
        ("SELECT 1; DELETE FROM t", "exactly one statement is required, got 2"),
        ("COPY t FROM PROGRAM 'id'", "CopyStmt"),
        ("SET statement_timeout = 0", "VariableSetStmt"),
        ("SET TRANSACTION READ WRITE", "VariableSetStmt"),
        ("DO $$ BEGIN RAISE NOTICE 'hi'; END $$", "DoStmt"),
        ("CALL p_procedure()", "CallStmt"),
        ("MERGE INTO t USING s ON t.a = s.a WHEN MATCHED THEN DELETE", "MergeStmt"),
        ("TRUNCATE t", "TruncateStmt"),
        ("GRANT SELECT ON t TO readonly_mcp", "GrantStmt"),
        ("INSERT INTO t VALUES (1)", "InsertStmt"),
        ("insert into t values (1)", "InsertStmt"),
        ("UPDATE t SET a = 1", "UpdateStmt"),
        ("DELETE FROM t", "DeleteStmt"),
        ("DROP TABLE t", "DropStmt"),
        ("CREATE TABLE x(a int)", "CreateStmt"),
        ("ALTER TABLE t ADD COLUMN b INT", "AlterTableStmt"),
        ("COMMIT", "TransactionStmt"),
        ("DISCARD ALL", "DiscardStmt"),
    ],
    ids=[
        "stacked-select-delete",
        "copy-program",
        "set-timeout",
        "set-transaction",
        "do-block",
        "call-procedure",
        "merge",
        "truncate",
        "grant",
        "insert-plain",
        "insert-lowercase",
        "update-plain",
        "delete-plain",
        "drop",
        "create",
        "alter",
        "commit-closed",
        "discard-closed",
    ],
)
def test_utility_write_path_denied(sql, node):
    if node.startswith("exactly one"):
        assert classify(sql, False) == Verdict(
            allowed=False, denial=f"rejected: {node}", node=""
        )
    else:
        assert_statement_denial(sql, node)


# --- uc-dangerous-function: denylist in the closed gate --------------------------


@pytest.mark.parametrize(
    ("sql", "name"),
    [
        ("SELECT set_config('a', 'b', false)", "set_config"),
        ("SELECT pg_read_file('pg_hba.conf')", "pg_read_file"),
        ("SELECT * FROM pg_read_file('pg_hba.conf')", "pg_read_file"),
        ("SELECT pg_ls_dir('.')", "pg_ls_dir"),
        ("SELECT lo_creat(-1)", "lo_creat"),
        ("SELECT lo_import('/tmp/x')", "lo_import"),
        ("SELECT nextval('s_seq')", "nextval"),
        ("SELECT currval('s_seq')", "currval"),
        ("SELECT setval('s_seq', 1)", "setval"),
        ("SELECT pg_sleep(0.1)", "pg_sleep"),
        ("SELECT * FROM pg_sleep(0.1)", "pg_sleep"),
        ("SELECT * FROM pg_catalog.pg_read_file('x')", "pg_read_file"),
        ("SELECT pg_catalog.set_config('a', 'b', false)", "set_config"),
        ("SELECT pg_terminate_backend(1)", "pg_terminate_backend"),
        ("SELECT pg_cancel_backend(1)", "pg_cancel_backend"),
        ("SELECT pg_signal_backend(1, 2)", "pg_signal_backend"),
        ("SELECT pg_reload_conf()", "pg_reload_conf"),
        ("SELECT pg_rotate_logfile()", "pg_rotate_logfile"),
        ("SELECT pg_read_binary_file('x')", "pg_read_binary_file"),
        ("SELECT pg_stat_file('x')", "pg_stat_file"),
        ("SELECT dblink_exec('c', 's')", "dblink_exec"),
        ("SELECT PG_SLEEP(0.1)", "pg_sleep"),
        ("SELECT * FROM t WHERE x IN (SELECT pg_sleep(1))", "pg_sleep"),
        ("SELECT * FROM (SELECT pg_sleep(1)) q", "pg_sleep"),
        ("SELECT * FROM t WHERE f(set_config('a', 'b', false))", "set_config"),
        ("EXPLAIN SELECT pg_sleep(1)", "pg_sleep"),
    ],
    ids=[
        "set-config",
        "pg-read-file",
        "pg-read-file-from",
        "pg-ls-dir",
        "lo-creat",
        "lo-import",
        "nextval",
        "currval",
        "setval",
        "pg-sleep",
        "pg-sleep-from",
        "pg-catalog-qualified",
        "pg-catalog-set-config",
        "pg-terminate-backend",
        "pg-cancel-backend",
        "pg-signal-backend",
        "pg-reload-conf",
        "pg-rotate-logfile",
        "pg-read-binary-file",
        "pg-stat-file",
        "dblink-exec",
        "pg-sleep-uppercase",
        "pg-sleep-where-subquery",
        "pg-sleep-from-subselect",
        "set-config-nested-arg",
        "explain-select-denied-function",
    ],
)
def test_dangerous_function_denied_closed(sql, name):
    assert_function_denial(sql, name)


# --- reads that must keep passing -------------------------------------------------


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1 UNION SELECT 2 UNION SELECT 3",
        "WITH x AS (SELECT 1) SELECT * FROM x",
        "EXPLAIN SELECT 1",
        "TABLE t",
        "VALUES (1)",
        'SELECT "delete" FROM t',
        "SELECT '; DROP TABLE t'",
        "SELECT abs(-1)",
        "SELECT count(*) FROM t",
        "SELECT * FROM myfunc(1)",
    ],
    ids=[
        "nested-set-operations",
        "plain-cte",
        "explain-bare",
        "table-form",
        "values-form",
        "quoted-keyword-identifier",
        "string-literal-semicolon-drop",
        "allowed-function-abs",
        "allowed-function-count",
        "allowed-user-function-from",
    ],
)
def test_plain_reads_pass(sql):
    assert classify(sql, False) == Verdict(allowed=True, denial="", node="")


# --- empty input and parse errors ---------------------------------------------------


@pytest.mark.parametrize("sql", ["", "   "], ids=["empty-string", "whitespace-only"])
def test_empty_input_rejected(sql):
    assert classify(sql, False) == Verdict(
        allowed=False,
        denial="rejected: exactly one statement is required, got 0",
        node="",
    )


def test_parse_error_carries_pglast_message():
    verdict = classify("SELEC 1 FROM", False)
    assert verdict.allowed is False
    assert verdict.denial.startswith("rejected: could not parse SQL: ")
    assert "SELEC" in verdict.denial
    assert verdict.node == ""


# --- open gate: statement types open up, denylist stays on ---------------------------


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO t VALUES (1)",
        "WITH x AS (DELETE FROM t RETURNING *) SELECT * FROM x",
        "EXPLAIN ANALYZE SELECT * FROM t",
        "TRUNCATE t",
    ],
    ids=[
        "open-insert-allowed",
        "open-cte-write-allowed",
        "open-explain-analyze-allowed",
        "open-truncate-allowed",
    ],
)
def test_open_gate_allows_writes(sql):
    assert classify(sql, True) == Verdict(allowed=True, denial="", node="")


@pytest.mark.parametrize(
    ("sql", "name"),
    [
        ("SELECT pg_terminate_backend(1)", "pg_terminate_backend"),
        ("SELECT set_config('a', 'b', false)", "set_config"),
    ],
    ids=["open-pg-terminate-backend-denied", "open-set-config-denied"],
)
def test_open_gate_still_denies_functions(sql, name):
    assert_function_denial(sql, name, allow_writes=True)


@pytest.mark.parametrize(
    ("sql", "node"),
    [
        ("DO $$ BEGIN RAISE NOTICE 'hi'; END $$", "DoStmt"),
        ("COMMIT", "TransactionStmt"),
        ("SET statement_timeout = 0", "VariableSetStmt"),
        ("DISCARD ALL", "DiscardStmt"),
    ],
    ids=[
        "open-do-denied",
        "open-commit-denied",
        "open-set-denied",
        "open-discard-denied",
    ],
)
def test_open_gate_denies_session_statements(sql, node):
    assert_statement_denial(sql, node, allow_writes=True)


def test_open_gate_still_enforces_single_statement():
    assert classify("SELECT 1; SELECT 2", True) == Verdict(
        allowed=False,
        denial="rejected: exactly one statement is required, got 2",
        node="",
    )


def test_open_gate_parse_error_carries_message():
    verdict = classify("SELEC 1 FROM", True)
    assert verdict.allowed is False
    assert verdict.denial.startswith("rejected: could not parse SQL: ")
    assert verdict.node == ""


def test_open_gate_empty_input_rejected():
    assert classify("", True) == Verdict(
        allowed=False,
        denial="rejected: exactly one statement is required, got 0",
        node="",
    )


# --- Verdict shape and denylist normalisation ------------------------------------------


def test_allowed_verdict_shape():
    verdict = classify("SELECT 1", False)
    assert verdict.allowed is True
    assert verdict.denial == ""
    assert verdict.node == ""


def test_verdict_is_frozen():
    verdict = classify("SELECT 1", False)
    with pytest.raises(dataclasses.FrozenInstanceError):
        verdict.allowed = False  # type: ignore[misc]


def test_denied_functions_are_lowercase_unqualified():
    assert isinstance(DENIED_FUNCTIONS, frozenset)
    assert DENIED_FUNCTIONS
    assert all(entry == entry.lower() for entry in DENIED_FUNCTIONS)
    assert all("." not in entry for entry in DENIED_FUNCTIONS)


def test_denylist_match_is_case_insensitive():
    assert classify("SELECT PG_SLEEP(0.1)", False) == Verdict(
        allowed=False, denial=f"rejected: function pg_sleep {CLOSED}", node="pg_sleep"
    )
