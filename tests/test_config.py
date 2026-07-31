"""
Purpose: Unit tests for tagmanager settings loading and env overrides.
Author(s): John Reed
"""

from tagmanager.config import Settings, get_settings


def test_settings_defaults():
    settings = Settings()
    assert settings.db_url == "sqlite:///tagmanager.db"
    assert settings.auth_mode == "none"
    assert settings.scan_interval_minutes == 60


def test_settings_env_override(monkeypatch):
    monkeypatch.setenv("TAGMANAGER_DB_URL", "postgresql://u:p@h/db")
    monkeypatch.setenv("TAGMANAGER_AUTH_MODE", "oidc")
    settings = Settings()
    assert settings.db_url == "postgresql://u:p@h/db"
    assert settings.auth_mode == "oidc"


def test_get_settings_returns_settings():
    assert isinstance(get_settings(), Settings)
