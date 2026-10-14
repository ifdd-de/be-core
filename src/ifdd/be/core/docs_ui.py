"""Swagger UI and ReDoc pages that work under a strict Content-Security-Policy.

FastAPI's own ``/docs`` page starts Swagger UI with an inline ``<script>``
and loads it from a CDN. Behind the IFDD proxy, whose policy for the backend
allows no inline scripts, that page stays empty; so does its OAuth2 redirect
page, which is an inline script too. This module replaces both, and the
ReDoc page:

* the pages contain no inline script and no inline style: Swagger UI is
  started by ``docs_assets/ifdd/swagger-init.js``, which reads the values of
  the instance from ``data-*`` attributes;
* Swagger UI and ReDoc are served by the backend itself from
  ``docs_assets/`` (exact versions, checked by SHA-256, see
  ``docs_assets/assets.json``), so the pages need no CDN and work without
  Internet access.

The pages and the OpenAPI document are open: they describe the API, they do
not give access to data. "Authorize" in Swagger UI logs in with the
authorization code flow and PKCE at the realm; every data endpoint still
checks the access token and its roles.

Paths:

=========================  ===============================================
``/docs``                  Swagger UI
``/docs/oauth2-redirect``  where the realm sends the browser back after login
``/redoc``                 ReDoc
``/docs/assets/...``       the static files of both
=========================  ===============================================
"""

from __future__ import annotations

from html import escape
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request
from starlette.responses import HTMLResponse

from .config import CoreSettings

ASSETS_DIR = Path(__file__).parent / "docs_assets"

DOCS_PATH = "/docs"
OAUTH2_REDIRECT_PATH = "/docs/oauth2-redirect"
REDOC_PATH = "/redoc"
ASSETS_PATH = "/docs/assets"

# Scopes requested by "Authorize"; the same as the OpenAPI security scheme.
OAUTH2_SCOPES = "openid profile email"


def install_docs(app: FastAPI, settings: CoreSettings) -> None:
    """Add the documentation pages and their static files to an application.

    Call it before routers with catch-all paths are included: the generic
    ``/{node_aspect}/{node_id}`` routes would otherwise also match
    ``/docs/oauth2-redirect``.

    Args:
        app: The application, created with ``docs_url=None`` and
            ``redoc_url=None`` so that FastAPI's own pages do not exist.
        settings: The active settings; the OIDC client for "Authorize" is
            ``IFDD_OIDC_JWKS_AUDIENCE``, and there is no login button when
            ``IFDD_BE_AUTH_ENABLED`` is false.
    """
    app.mount(ASSETS_PATH, StaticFiles(directory=ASSETS_DIR), name="docs-assets")

    client_id = settings.IFDD_OIDC_JWKS_AUDIENCE if settings.IFDD_BE_AUTH_ENABLED else ""
    title = settings.API_TITLE

    async def swagger_ui(request: Request) -> HTMLResponse:
        """GET /docs."""
        return HTMLResponse(swagger_ui_html(_prefix(request), app.openapi_url, title, client_id))

    async def swagger_ui_redirect(request: Request) -> HTMLResponse:
        """GET /docs/oauth2-redirect."""
        return HTMLResponse(oauth2_redirect_html(_prefix(request)))

    async def redoc(request: Request) -> HTMLResponse:
        """GET /redoc."""
        return HTMLResponse(redoc_html(_prefix(request), app.openapi_url, title))

    app.add_api_route(DOCS_PATH, swagger_ui, methods=["GET"], include_in_schema=False)
    app.add_api_route(
        OAUTH2_REDIRECT_PATH, swagger_ui_redirect, methods=["GET"], include_in_schema=False
    )
    app.add_api_route(REDOC_PATH, redoc, methods=["GET"], include_in_schema=False)


def _prefix(request: Request) -> str:
    """The ``root_path`` the application runs under, without a trailing slash."""
    return request.scope.get("root_path", "").rstrip("/")


def swagger_ui_html(prefix: str, openapi_url: str, title: str, client_id: str) -> str:
    """The Swagger UI page.

    Args:
        prefix: ``root_path`` of the application ("" behind the IFDD proxy).
        openapi_url: Path of the OpenAPI document, e.g. ``/openapi.json``.
        title: Title of the API, shown in the browser tab.
        client_id: OIDC client used by "Authorize"; "" hides the login.

    Returns:
        A complete HTML page without inline script or style.
    """
    a = _attribute
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)} - Swagger UI</title>
<link rel="stylesheet" href="{a(prefix + ASSETS_PATH)}/swagger-ui/swagger-ui.css">
</head>
<body>
<noscript>Swagger UI needs JavaScript.
The OpenAPI document is at {escape(prefix + openapi_url)}.</noscript>
<div id="swagger-ui"
     data-openapi-url="{a(prefix + openapi_url)}"
     data-oauth2-redirect-url="{a(prefix + OAUTH2_REDIRECT_PATH)}"
     data-client-id="{a(client_id)}"
     data-scopes="{a(OAUTH2_SCOPES)}"></div>
<script src="{a(prefix + ASSETS_PATH)}/swagger-ui/swagger-ui-bundle.js"></script>
<script src="{a(prefix + ASSETS_PATH)}/ifdd/swagger-init.js"></script>
</body>
</html>
"""


def oauth2_redirect_html(prefix: str) -> str:
    """The page the realm redirects the browser to after "Authorize".

    It loads ``oauth2-redirect.js`` of swagger-ui-dist, which hands the
    authorization code to the Swagger UI window and closes itself.

    Args:
        prefix: ``root_path`` of the application.

    Returns:
        A complete HTML page without inline script.
    """
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Swagger UI: OAuth2 Redirect</title>
</head>
<body>
<script src="{_attribute(prefix + ASSETS_PATH)}/swagger-ui/oauth2-redirect.js"></script>
</body>
</html>
"""


def redoc_html(prefix: str, openapi_url: str, title: str) -> str:
    """The ReDoc page.

    ReDoc starts by itself on the ``<redoc spec-url>`` element; the page
    loads no web fonts.

    Args:
        prefix: ``root_path`` of the application.
        openapi_url: Path of the OpenAPI document.
        title: Title of the API, shown in the browser tab.

    Returns:
        A complete HTML page without inline script or style.
    """
    a = _attribute
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)} - ReDoc</title>
<link rel="stylesheet" href="{a(prefix + ASSETS_PATH)}/ifdd/docs.css">
</head>
<body>
<noscript>ReDoc needs JavaScript.
The OpenAPI document is at {escape(prefix + openapi_url)}.</noscript>
<redoc spec-url="{a(prefix + openapi_url)}"></redoc>
<script src="{a(prefix + ASSETS_PATH)}/redoc/redoc.standalone.js"></script>
</body>
</html>
"""


def _attribute(value: str) -> str:
    """A value escaped for a double-quoted HTML attribute."""
    return escape(value, quote=True)
