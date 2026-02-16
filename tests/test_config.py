"""Tests for SendparcelConfig."""

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
