"""Environment configuration (pure domain, no I/O).

Six ``PG_*`` variables in, one frozen ``PostgresConfig`` out. Row cap and
statement timeout are NOT here: they are the constants ``ROW_CAP`` and
``TIMEOUT_MS`` in ``postgres_mcp.infrastructure.adapters.postgres``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


class ConfigError(ValueError):
    """A malformed ``PG_*`` value; ``str(exc)`` is the fixed config error text."""


@dataclass(frozen=True)
class PostgresConfig:
    """Typed view of the six ``PG_*`` variables.

    ``PG_USER`` and ``PG_PASSWORD`` have no default: a missing or empty value
    is a ``ConfigError``. ``PG_ALLOW_WRITES`` keeps its raw string; only
    exactly ``"1"`` opens the gate (see :attr:`allow_writes`).
    """

    PG_USER: str
    PG_PASSWORD: str
    PG_HOST: str = "127.0.0.1"
    PG_PORT: int = 5423
    PG_DBNAME: str = "postgres"
    PG_ALLOW_WRITES: str = ""

    @property
    def allow_writes(self) -> bool:
        """True only when ``PG_ALLOW_WRITES`` is exactly ``"1"``."""
        return self.PG_ALLOW_WRITES == "1"


def _required(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "")
    if not value:
        raise ConfigError(f"missing required variable: {name}")
    return value


def load_config(env: Mapping[str, str]) -> PostgresConfig:
    """Validate ``env`` and return the frozen config; raise ``ConfigError`` loudly."""
    host = env.get("PG_HOST", "127.0.0.1")
    if not host:
        raise ConfigError("missing required variable: PG_HOST")
    raw_port = env.get("PG_PORT", "5423")
    try:
        port = int(raw_port)
    except (TypeError, ValueError):
        raise ConfigError(f"invalid PG_PORT {raw_port!r}: must be 1-65535") from None
    if not 1 <= port <= 65535:
        raise ConfigError(f"invalid PG_PORT {raw_port!r}: must be 1-65535")
    dbname = env.get("PG_DBNAME", "postgres")
    if not dbname:
        raise ConfigError("missing required variable: PG_DBNAME")
    return PostgresConfig(
        PG_USER=_required(env, "PG_USER"),
        PG_PASSWORD=_required(env, "PG_PASSWORD"),
        PG_HOST=host,
        PG_PORT=port,
        PG_DBNAME=dbname,
        PG_ALLOW_WRITES=env.get("PG_ALLOW_WRITES", ""),
    )
