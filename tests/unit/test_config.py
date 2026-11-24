"""Unit tests for postgres_mcp.domain.config (pure, no I/O)."""

import dataclasses

import pytest

from postgres_mcp.domain.config import ConfigError, load_config

BASE = {
    "PG_HOST": "127.0.0.1",
    "PG_PORT": "5423",
    "PG_USER": "app_user",
    "PG_PASSWORD": "s3cret",
    "PG_DBNAME": "postgres",
}


def test_valid_env_loads_all_fields():
    config = load_config(dict(BASE))
    assert config.PG_HOST == "127.0.0.1"
    assert config.PG_PORT == 5423
    assert config.PG_USER == "app_user"
    assert config.PG_PASSWORD == "s3cret"
    assert config.PG_DBNAME == "postgres"
    assert config.PG_ALLOW_WRITES == ""
    assert config.allow_writes is False


def test_unset_host_port_dbname_fall_back_to_defaults():
    config = load_config({"PG_USER": "u", "PG_PASSWORD": "p"})
    assert config.PG_HOST == "127.0.0.1"
    assert config.PG_PORT == 5423
    assert config.PG_DBNAME == "postgres"


def test_empty_host_is_missing():
    with pytest.raises(ConfigError, match=r"^missing required variable: PG_HOST$"):
        load_config({**BASE, "PG_HOST": ""})


def test_empty_dbname_is_missing():
    with pytest.raises(ConfigError, match=r"^missing required variable: PG_DBNAME$"):
        load_config({**BASE, "PG_DBNAME": ""})


@pytest.mark.parametrize("name", ["PG_USER", "PG_PASSWORD"])
@pytest.mark.parametrize("value", ["", None])
def test_missing_or_empty_credential_is_missing(name, value):
    env = dict(BASE)
    if value is None:
        del env[name]
    else:
        env[name] = value
    with pytest.raises(ConfigError, match=rf"^missing required variable: {name}$"):
        load_config(env)


@pytest.mark.parametrize(
    "value", ["abc", "", "0", "-1", "65536", "99999", "54.23", "0x10"]
)
def test_malformed_port_fails_with_fixed_text(value):
    with pytest.raises(
        ConfigError, match=rf"^invalid PG_PORT {value!r}: must be 1-65535$"
    ):
        load_config({**BASE, "PG_PORT": value})


@pytest.mark.parametrize("value", ["1", "1024", "5432", "65535"])
def test_port_boundaries_pass(value):
    assert load_config({**BASE, "PG_PORT": value}).PG_PORT == int(value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1", True),
        ("", False),
        ("0", False),
        ("true", False),
        (" 1", False),
        ("11", False),
    ],
    ids=[
        "exactly-one-opens",
        "empty-closed",
        "zero-closed",
        "true-closed",
        "padded-closed",
        "eleven-closed",
    ],
)
def test_allow_writes_is_exactly_one(value, expected):
    assert load_config({**BASE, "PG_ALLOW_WRITES": value}).allow_writes is expected


def test_config_is_frozen():
    config = load_config(dict(BASE))
    with pytest.raises(dataclasses.FrozenInstanceError):
        config.PG_HOST = "other"  # type: ignore[misc]


def test_config_error_is_a_value_error():
    assert issubclass(ConfigError, ValueError)
