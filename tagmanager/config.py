"""
Purpose: Settings for TagManager — env-driven config with TAGMANAGER_ prefix.
Author(s): John Reed
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App settings; every field overridable via TAGMANAGER_<FIELD> env var."""

    model_config = SettingsConfigDict(env_prefix="TAGMANAGER_")

    db_url: str = "sqlite:///tagmanager.db"
    auth_mode: str = "none"
    oidc_issuer: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    scan_interval_minutes: int = 60
    age_band_days: list = [90, 365]
    storage_prefix_depth: int = 2


def get_settings():
    """
    Build a Settings instance from the environment.

    :returns: Settings
    """
    return Settings()
