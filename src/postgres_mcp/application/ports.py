"""S-out port: the single seam (one interface) of the whole design.

``ExecutorPort`` is the only abstract base class anywhere in the tree; the
stdio side (S-in) is a concrete handler, not an abstraction.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class QueryResult:
    """One bounded result set: at most ``ROW_CAP`` rows plus the truncated flag."""

    columns: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]
    truncated: bool
    row_count: int


class ExecutorPort(ABC):
    """Outbound Postgres seam; only ``PsycopgExecutor`` implements this."""

    @abstractmethod
    def execute(self, sql: str, read_only: bool) -> QueryResult:
        """Run one allowed statement. Only PsycopgExecutor implements this."""
