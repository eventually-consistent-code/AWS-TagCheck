"""
Purpose: OIDC login for the TagManager UI/API with a dev bypass mode.
Author(s): John Reed
"""

import logging
import os
import secrets

from authlib.integrations.starlette_client import OAuth
from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
LOG = logging.getLogger("root.auth")
LOG.setLevel(logging.INFO)

OPEN_PATHS = ("/api/health", "/login", "/auth/callback")


class RequireUserMiddleware(BaseHTTPMiddleware):  # pylint: disable=too-few-public-methods
    """HTTP middleware rejecting unauthenticated requests to gated paths."""

    async def dispatch(self, request: Request, call_next):
        """401 for anything but the open paths when not logged in."""
        if request.url.path in OPEN_PATHS:
            return await call_next(request)
        if not request.session.get("user"):
            return JSONResponse({"title": "unauthorized", "status": 401},
                                status_code=401)
        return await call_next(request)


def install_auth(app, settings):
    """
    Wire session + OIDC auth onto the app; no-op when auth_mode is none.

    :param app: FastAPI app
    :param settings: Settings
    :raises ValueError: if auth_mode is not 'none' or 'oidc'
    """
    if settings.auth_mode == "none":
        LOG.info("auth mode none — running open (dev only)...")
        return
    if settings.auth_mode != "oidc":
        raise ValueError(
            f"unrecognized auth_mode: {settings.auth_mode!r} (expected 'none' or 'oidc')")

    app.add_middleware(RequireUserMiddleware)
    app.add_middleware(SessionMiddleware, secret_key=os.environ.get(
        "TAGMANAGER_SESSION_SECRET", secrets.token_hex(32)))

    oauth = OAuth()
    oauth.register(
        name="idp",
        client_id=settings.oidc_client_id,
        client_secret=settings.oidc_client_secret,
        server_metadata_url=(
            f"{settings.oidc_issuer}/.well-known/openid-configuration"),
        client_kwargs={"scope": "openid email profile"},
    )

    @app.get("/login")
    async def login(request: Request):
        """Send the user to the IdP."""
        redirect_uri = request.url_for("auth_callback")
        return await oauth.idp.authorize_redirect(request, redirect_uri)

    @app.get("/auth/callback")
    async def auth_callback(request: Request):
        """Complete the code flow, stash the user in the session."""
        token = await oauth.idp.authorize_access_token(request)
        info = token.get("userinfo") or {}
        request.session["user"] = {"email": info.get("email", ""),
                                   "name": info.get("name", "")}
        LOG.info("login ok... %s", info.get("email", "?"))
        return RedirectResponse(url="/")

    @app.get("/logout")
    async def logout(request: Request):
        """Drop the session."""
        request.session.clear()
        return RedirectResponse(url="/login")
