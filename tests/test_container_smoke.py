#!/usr/bin/env python

"""
Purpose: Smoke test — the serve entrypoint wiring boots against SQLite.
Author(s): John Reed
"""

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from tagmanager.app.main import create_app
from tagmanager.config import Settings
from tagmanager.models.base import create_all, session_factory
# Import all table models to register them with Base
from tagmanager.models import tables  # pylint: disable=unused-import
from tagmanager.providers.aws_provider import AwsProvider
from tagmanager.providers.azure_provider import AzureProvider
from tagmanager.providers.gcp_provider import GcpProvider
from tagmanager.serve import _scopes_loader


def test_full_wiring_boots_and_serves():
    """Test that the full wiring boots and serves HTTP requests."""
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    create_all(engine)
    maker = session_factory(engine)
    providers = {"aws": AwsProvider(), "azure": AzureProvider(),
                 "gcp": GcpProvider()}
    assert set(providers) == {"aws", "azure", "gcp"}
    assert _scopes_loader(maker)() == []
    client = TestClient(create_app(Settings(auth_mode="none"), maker))
    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/").status_code == 200
