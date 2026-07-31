"""
Purpose: Auth tests — dev bypass leaves API open; oidc mode gates routes.
Author(s): John Reed
"""

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from tagmanager.app.main import create_app
from tagmanager.config import Settings
from tagmanager.models.base import create_all, session_factory


def _client(auth_mode):
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    create_all(engine)
    settings = Settings(auth_mode=auth_mode, oidc_issuer="https://idp.example",
                        oidc_client_id="cid", oidc_client_secret="secret")
    return TestClient(create_app(settings, session_factory(engine)))


def test_none_mode_leaves_api_open():
    """Auth mode none leaves API open."""
    assert _client("none").get("/api/resources").status_code == 200


def test_oidc_mode_rejects_anonymous_api():
    """Auth mode oidc rejects unauthenticated API access."""
    assert _client("oidc").get("/api/resources").status_code == 401


def test_oidc_mode_health_stays_open():
    """Auth mode oidc leaves health check open."""
    assert _client("oidc").get("/api/health").status_code == 200


def test_oidc_mode_login_redirects_to_idp(httpx_mock):
    """Login route redirects to IdP (mocks OIDC metadata fetch)."""
    # Mock the OIDC metadata endpoint
    metadata = {
        "authorization_endpoint": "https://idp.example/authorize",
        "token_endpoint": "https://idp.example/token",
        "userinfo_endpoint": "https://idp.example/userinfo",
        "jwks_uri": "https://idp.example/jwks",
    }
    httpx_mock.add_response(
        method="GET",
        url="https://idp.example/.well-known/openid-configuration",
        json=metadata)

    response = _client("oidc").get("/login", follow_redirects=False)
    assert response.status_code in (302, 307)
