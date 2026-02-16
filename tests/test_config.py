"""Tests for SendparcelConfig."""

import pytest
from pydantic import ValidationError

from litestar_sendparcel.config import SendparcelConfig


def test_config_defaults():
    """Config has retry defaults."""
    config = SendparcelConfig(default_provider="dummy")
    assert config.retry_max_attempts == 5
    assert config.retry_backoff_seconds == 60
    assert config.retry_enabled is True
    assert config.providers == {}


def test_config_custom_retry():
    """Config accepts custom retry settings."""
    config = SendparcelConfig(
        default_provider="inpost",
        retry_max_attempts=3,
        retry_backoff_seconds=30,
        retry_enabled=False,
    )
    assert config.retry_max_attempts == 3
    assert config.retry_backoff_seconds == 30
    assert config.retry_enabled is False


def test_config_env_prefix(monkeypatch):
    """Config reads from SENDPARCEL_ env vars."""
    monkeypatch.setenv("SENDPARCEL_DEFAULT_PROVIDER", "inpost")
    monkeypatch.setenv("SENDPARCEL_RETRY_MAX_ATTEMPTS", "10")
    config = SendparcelConfig()
    assert config.default_provider == "inpost"
    assert config.retry_max_attempts == 10


def test_default_provider_required():
    """Config must fail without default_provider."""
    with pytest.raises(ValidationError):
        SendparcelConfig()


def test_default_provider_accepted():
    """Config accepts a default_provider string."""
    cfg = SendparcelConfig(default_provider="inpost")
    assert cfg.default_provider == "inpost"


def test_providers_accepts_nested_dict():
    """providers accepts nested provider config dicts."""
    cfg = SendparcelConfig(
        default_provider="x",
        providers={"inpost": {"api_key": "abc"}},
    )
    assert cfg.providers["inpost"]["api_key"] == "abc"


def test_retry_enabled_default():
    """retry_enabled defaults to True."""
    cfg = SendparcelConfig(default_provider="x")
    assert cfg.retry_enabled is True
