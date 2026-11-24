"""Live config suite: real PG18, ``postgres`` database only.

Covers ``uc-config-env``, positive and negative. The positive case loads
the real role credentials and actually connects; the negative cases use
fake sentinels and never touch the network.
"""

import pytest

from postgres_mcp.domain.config import ConfigError, load_config

from ..conftest import DBNAME, HOST, PORT, ROLE, LiveDb


def test_live_config_env_pos(live: LiveDb) -> None:
    config = live.config()
    assert config.PG_HOST == HOST
    assert config.PG_PORT == PORT
    assert config.PG_DBNAME == DBNAME
    assert config.PG_USER == ROLE
    assert config.allow_writes is False
    assert live.call("SELECT 1")["rows"] == [(1,)]


@pytest.mark.parametrize(
    ("name", "value", "error"),
    [
        ("PG_PORT", "abc", "invalid PG_PORT 'abc': must be 1-65535"),
        ("PG_PORT", "99999", "invalid PG_PORT '99999': must be 1-65535"),
        ("PG_HOST", "(empty)", "missing required variable: PG_HOST"),
        ("PG_USER", "(empty)", "missing required variable: PG_USER"),
        ("PG_PASSWORD", "(empty)", "missing required variable: PG_PASSWORD"),
    ],
)
def test_live_config_env_neg(name: str, value: str, error: str) -> None:
    env = {
        "PG_HOST": "127.0.0.1",
        "PG_PORT": "5423",
        "PG_USER": "app_user",
        "PG_PASSWORD": "s3cret",
        "PG_DBNAME": "postgres",
    }
    env[name] = "" if value == "(empty)" else value
    with pytest.raises(ConfigError) as excinfo:
        load_config(env)
    assert error in str(excinfo.value)
