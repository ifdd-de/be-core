"""Application factory.

An instance calls :func:`create_app` after registering its own settings.  The
factory owns everything that was previously written out at module level in the
generated ``main.py``: middleware, CORS, the documentation pages, the OpenAPI
document and the router wiring.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Iterable, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRouter
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from .config import CoreSettings, configure, get_settings
from .docs_ui import install_docs
from .jsonld import install_document_loader
from .logging import setup_logger
from .openapi import build_openapi
from .routers import (
    build_aspect_router,
    graph_data_router,
    nodes_router,
    scopes_router,
    types_router,
    versions_router,
)
from .version import __version__


def create_app(
    settings: Optional[CoreSettings] = None,
    extra_routers: Optional[Iterable[APIRouter]] = None,
) -> FastAPI:
    """Create and wire the FastAPI application.

    Args:
        settings: Settings of the instance. They are registered with
            :func:`~ifdd.be.core.config.configure`; without them the settings
            are read from the environment.
        extra_routers: The extension point for instance-specific endpoints
            that must not live in the shared core. They are included after
            the generic routers and before the catch-all document routes.

    Returns:
        The application, ready for uvicorn (``uvicorn --factory
        ifdd.be.core:create_app`` or an instance's ``app.main:app``).
    """
    if settings is not None:
        configure(settings)
    settings = get_settings()

    logger = setup_logger(__name__)
    install_document_loader()
    logger.info(
        f"Starting {settings.API_TITLE} {settings.IFDD_BE_VERSION} (ifdd-be-core {__version__})"
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        """Close the database engine when the application stops."""
        yield
        from .db.session import _session_manager

        if _session_manager is not None:
            await _session_manager.close()

    # FastAPI's own /docs and /redoc pages use inline scripts and a CDN; the
    # pages of docs_ui replace them (see that module).
    app = FastAPI(
        title=settings.API_TITLE,
        version=settings.IFDD_BE_VERSION,
        debug=settings.DEBUG,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        swagger_ui_oauth2_redirect_url=None,
    )

    app.add_middleware(
        SessionMiddleware,
        https_only=settings.IFDD_BE_SSL_ENABLED,
        secret_key=settings.FASTAPI_SECRET_KEY,
    )

    logger.debug(f"Allowed origins: {settings.IFDD_CORS_ORIGINS}")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.IFDD_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Total-Count", "Content-Range"],
    )

    limiter = Limiter(key_func=get_remote_address)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)

    # Before every router: /docs/oauth2-redirect has two path segments and
    # would otherwise be taken by GET /{node_aspect}/{node_id}.
    install_docs(app, settings)

    app.include_router(versions_router)
    app.include_router(types_router)
    app.include_router(scopes_router)
    app.include_router(graph_data_router)
    app.include_router(build_aspect_router(settings.IFDD_ASPECTS))
    for router in extra_routers or ():
        app.include_router(router)
    # The catch-all /{node_aspect}/{node_id} routes are registered last so that
    # they never shadow a more specific path.
    app.include_router(nodes_router)

    app.openapi = build_openapi(app, settings)
    return app


def _rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Answer 429 when a slowapi limit is exceeded.

    No route carries a limit at the moment; the handler is kept for instance
    routers that add one.
    """
    return JSONResponse(status_code=429, content={"message": "Rate limit exceeded"})
