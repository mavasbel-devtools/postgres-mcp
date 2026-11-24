"""Unit tests for postgres_mcp.application.ports (the one interface)."""

import dataclasses

import pytest

from postgres_mcp.application.ports import ExecutorPort, QueryResult


def test_query_result_shape():
    result = QueryResult(
        columns=("n",), rows=((1,), (2,)), truncated=False, row_count=2
    )
    assert result.columns == ("n",)
    assert result.rows == ((1,), (2,))
    assert result.truncated is False
    assert result.row_count == 2


def test_query_result_is_frozen():
    result = QueryResult(columns=(), rows=(), truncated=False, row_count=0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.row_count = 1  # type: ignore[misc]


def test_executor_port_cannot_be_instantiated():
    with pytest.raises(TypeError):
        ExecutorPort()  # type: ignore[abstract]


def test_abstract_body_documents_the_contract():
    class Stub(ExecutorPort):
        def execute(self, sql: str, read_only: bool) -> QueryResult:
            return QueryResult(columns=(), rows=(), truncated=False, row_count=0)

    assert ExecutorPort.execute(Stub(), "SELECT 1", True) is None
