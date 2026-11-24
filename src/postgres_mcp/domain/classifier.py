"""Read-only SQL gate (pure domain function, no I/O).

Closed gate (``allow_writes`` is false): pass only one bare ``SelectStmt``
(or a bare ``EXPLAIN`` over one). Open gate: pass one statement of any
type except ``TransactionStmt``, ``VariableSetStmt``, ``DiscardStmt``,
``DoStmt``. Both gates enforce ``DENIED_FUNCTIONS`` and ``n_stmts == 1``.

Parsing uses ``pglast.parse_sql``, so keywords hidden in comments, quoted
identifiers, or string literals can never smuggle a statement type or a
function name past the check: only real node types and real ``FuncCall``
names decide.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import pglast
from pglast import ast

DENIED_FUNCTIONS: frozenset[str] = frozenset(
    {
        "pg_read_file",
        "pg_read_binary_file",
        "pg_ls_dir",
        "pg_stat_file",
        "set_config",
        "pg_terminate_backend",
        "pg_cancel_backend",
        "pg_reload_conf",
        "pg_rotate_logfile",
        "pg_sleep",
        "pg_signal_backend",
        "nextval",
        "currval",
        "setval",
        "lastval",
        "lo_*",
        "dblink*",
    }
)

_OPEN_DENIED = (
    ast.TransactionStmt,
    ast.VariableSetStmt,
    ast.DiscardStmt,
    ast.DoStmt,
)


@dataclass(frozen=True)
class Verdict:
    """Gate outcome: ``denial``/``node`` are empty exactly when allowed."""

    allowed: bool
    denial: str
    node: str


_ALLOWED = Verdict(allowed=True, denial="", node="")


def _deny(node: str) -> Verdict:
    return Verdict(
        allowed=False,
        denial=f"rejected: {node} is not allowed while PG_ALLOW_WRITES is closed",
        node=node,
    )


def _deny_function(name: str) -> Verdict:
    return Verdict(
        allowed=False,
        denial=f"rejected: function {name} is not allowed while PG_ALLOW_WRITES is closed",
        node=name,
    )


def _walk(node: ast.Node) -> Iterator[ast.Node]:
    """Yield ``node`` and every descendant node, depth first."""
    yield node
    for attr in dir(node):
        if attr.startswith("_") or attr == "ancestors":
            continue
        value = getattr(node, attr, None)
        if isinstance(value, ast.Node):
            yield from _walk(value)
        elif isinstance(value, (tuple, list)):
            for item in value:
                yield from _walk_value(item)


def _walk_value(value: object) -> Iterator[ast.Node]:
    if isinstance(value, ast.Node):
        yield from _walk(value)
    elif isinstance(value, (tuple, list)):
        for item in value:
            yield from _walk_value(item)


def _is_denied(lower: str) -> bool:
    """Match a lowercased unqualified function name; ``*`` ends a prefix."""
    for entry in sorted(DENIED_FUNCTIONS):
        if entry.endswith("*"):
            if lower.startswith(entry[:-1]):
                return True
        elif lower == entry:
            return True
    return False


def _find_denied_function(top: ast.Node) -> str | None:
    for node in _walk(top):
        if isinstance(node, ast.FuncCall) and node.funcname:
            name = node.funcname[-1].sval.lower()
            if _is_denied(name):
                return name
    return None


def _check_select_tree(top: ast.SelectStmt) -> Verdict:
    """Reject ``SELECT INTO``/``FOR UPDATE`` and non-``SelectStmt`` CTE bodies."""
    for node in _walk(top):
        if isinstance(node, ast.SelectStmt):
            if node.intoClause is not None:
                return _deny("IntoClause")
            if node.lockingClause:
                return _deny("LockingClause")
        elif isinstance(node, ast.CommonTableExpr):
            if not isinstance(node.ctequery, ast.SelectStmt):
                return _deny(type(node.ctequery).__name__)
    return _ALLOWED


def classify(sql: str, allow_writes: bool) -> Verdict:
    """Decide allow/deny for ``sql`` with zero I/O."""
    try:
        stmts = pglast.parse_sql(sql)
    except Exception as exc:
        return Verdict(
            allowed=False, denial=f"rejected: could not parse SQL: {exc}", node=""
        )
    if len(stmts) != 1:
        return Verdict(
            allowed=False,
            denial=f"rejected: exactly one statement is required, got {len(stmts)}",
            node="",
        )
    top = stmts[0].stmt
    denied = _find_denied_function(top) if top is not None else None
    if denied is not None:
        return _deny_function(denied)
    if allow_writes:
        if isinstance(top, _OPEN_DENIED):
            return _deny(type(top).__name__)
        return _ALLOWED
    if isinstance(top, ast.ExplainStmt):
        if top.options:
            return _deny("ExplainStmt with options")
        if not isinstance(top.query, ast.SelectStmt):
            return _deny(type(top.query).__name__)
        return _check_select_tree(top.query)
    if not isinstance(top, ast.SelectStmt):
        return _deny(type(top).__name__)
    return _check_select_tree(top)
