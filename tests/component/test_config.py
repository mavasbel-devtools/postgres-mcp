"""Component-tier config edge cases the feature scenarios do not pin down.

The ``uc-config-env`` scenarios cover every ``load_config`` line but one
(empty ``PG_DBNAME``); that case plus the documented defaults live here so
the component tier covers the config module fully with no I/O.
"""

import dataclasses

import pytest

from postgres_mcp.domain.config import ConfigError, load_config


def test_empty_dbname_is_missing():
    with pytest.raises(ConfigError, match=r"^missing required variable: PG_DBNAME$"):
        load_config(
            {
                "PG_HOST": "127.0.0.1",
                "PG_PORT": "5423",
                "PG_USER": "u",
                "PG_PASSWORD": "p",
                "PG_DBNAME": "",
            }
        )


def test_unset_host_port_dbname_fall_back_to_defaults():
    config = load_config({"PG_USER": "u", "PG_PASSWORD": "p"})
    assert config.PG_HOST == "127.0.0.1"
    assert config.PG_PORT == 5423
    assert config.PG_DBNAME == "postgres"


@pytest.mark.parametrize(
    ("value", "expected"),
    [("1", True), ("", False), ("0", False), ("true", False)],
    ids=["exactly-one-opens", "empty-closed", "zero-closed", "true-closed"],
)
def test_allow_writes_is_exactly_one(value, expected):
    env = {"PG_USER": "u", "PG_PASSWORD": "p", "PG_ALLOW_WRITES": value}
    assert load_config(env).allow_writes is expected


def test_config_is_frozen():
    config = load_config({"PG_USER": "u", "PG_PASSWORD": "p"})
    with pytest.raises(dataclasses.FrozenInstanceError):
        config.PG_DBNAME = "other"  # type: ignore[misc]
