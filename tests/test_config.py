"""Configuration tests."""

from fastapi_sendparcel.config import SendparcelConfig


def test_default_retry_settings() -> None:
    config = SendparcelConfig(default_provider="dummy")
    assert config.retry_max_attempts == 5
    assert config.retry_backoff_seconds == 60
    assert config.retry_enabled is True


def test_env_prefix(monkeypatch) -> None:
    monkeypatch.setenv("SENDPARCEL_DEFAULT_PROVIDER", "inpost")
    monkeypatch.setenv("SENDPARCEL_RETRY_MAX_ATTEMPTS", "10")
    monkeypatch.setenv("SENDPARCEL_RETRY_ENABLED", "false")

    config = SendparcelConfig()
    assert config.default_provider == "inpost"
    assert config.retry_max_attempts == 10
    assert config.retry_enabled is False


def test_providers_default_empty() -> None:
    config = SendparcelConfig(default_provider="dummy")
    assert config.providers == {}


def test_custom_retry_settings() -> None:
    config = SendparcelConfig(
        default_provider="dummy",
        retry_max_attempts=3,
        retry_backoff_seconds=30,
        retry_enabled=False,
    )
    assert config.retry_max_attempts == 3
    assert config.retry_backoff_seconds == 30
    assert config.retry_enabled is False
