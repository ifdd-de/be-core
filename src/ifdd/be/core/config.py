"""Core settings and the settings registry.

Instances subclass :class:`CoreSettings` and register their instance via
:func:`configure` before the application is created.  Every consumer inside
ifdd.be.core resolves the settings through :func:`get_settings` at call time, never
at import time, so import order never matters.

All values come from the environment or from ``.env`` (pydantic-settings);
unknown variables are ignored, so a ``.env`` may carry values for other tools
(``POSTGRES_PASSWORD``, ``WORKERS``) and settings that were removed (such as
``API_VERSION``) do no harm.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Type

from pydantic_settings import BaseSettings, SettingsConfigDict

from .version import __version__


class CoreSettings(BaseSettings):
    """Settings shared by every IFDD backend instance.

    The fields are grouped by concern; the comments next to them say what
    each one does. The ones an instance usually sets in its ``.env`` are:

    * ``IFDD_SERVICE_DB_URL`` -- the PostgreSQL connection URL;
    * the ``IFDD_OIDC_*`` values of the realm and ``IFDD_BE_AUTH_ENABLED``;
    * the role names ``IFDD_ROLE_*`` and ``IFDD_CONTEXT_ROOT``;
    * ``IFDD_SCHEMA_URL`` and ``IFDD_ASPECTS``;
    * ``IFDD_CORS_ORIGINS`` -- the browser origin of the UI.

    ``IFDD_BE_VERSION`` is the version of the instance; it is shown by
    ``/version``, ``/prot_version`` and the OpenAPI document. Its default is
    the version of this package.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # API
    # Title and summary of the OpenAPI document; the version shown there is
    # IFDD_BE_VERSION.
    API_TITLE: str = "IFDD Backend"
    API_SUMMARY: str = "JSON-LD backend of an IFDD node"
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_PERIOD: int = 60

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    LOG_TO_FILE: bool = False
    LOG_FILE_PATH: str = "logs/ifdd_backend.log"

    # Cache
    MEMCACHED_HOST: str = "memcached"
    MEMCACHED_PORT: int = 11211
    CACHE_DEFAULT_TIMEOUT: int = 300
    JSONLD_CACHE_EXPIRE_AFTER: int = 120
    JSONLD_LOADER_TIMEOUT: int = 10

    # OIDC
    IFDD_OIDC_TOKEN_URL: str = ""
    IFDD_OIDC_AUTHORIZATION_URL: str = ""
    IFDD_OIDC_REFRESH_URL: str = ""
    IFDD_OIDC_JWKS_URL: str = ""
    IFDD_OIDC_JWKS_AUDIENCE: str = ""
    IFDD_OIDC_JWKS_ALGORITHM: str = "RS256"
    # Expected "iss" of access tokens, e.g. https://id/realms/ifddtest.
    # Empty: not checked (a warning is logged); set it in every instance.
    IFDD_OIDC_ISSUER: str = ""
    IFDD_TOKEN_CACHE_SIZE: int = 1000
    IFDD_TOKEN_CACHE_TTL: int = 300
    # Client roles of IFDD_OIDC_JWKS_AUDIENCE (resource_access.<audience>.roles)
    IFDD_ROLE_PUBLIC: str = "ifdd_public"          # signed in, no further rights
    IFDD_ROLE_NODES_READ: str = "ifdd_nodes_ro"
    IFDD_ROLE_NODES_WRITE: str = "ifdd_nodes_rw"
    # Context pattern of the development user (IFDD_BE_AUTH_ENABLED=false):
    # it may use every domain context below this name (see contexts.py).
    IFDD_CONTEXT_ROOT: str = "ifdd.de"

    # Backend
    # Version of the instance; the template sets it from ifdd_be_version.
    IFDD_BE_VERSION: str = __version__
    IFDD_BE_HOST: str = "data"
    IFDD_BE_PORT: int = 8881
    IFDD_TYPE_URL: str = "http://type/v1"
    IFDD_SCHEMA_URL: str = "http://schema/v1"
    IFDD_SERVICE_DB_URL: str = ""
    # Keep retired versions as history in system time (True), or keep only
    # what is known now and delete what a write replaces (False). The valid
    # time periods of a document are kept either way.
    IFDD_VERSIONING: bool = True

    # CORS
    IFDD_CORS_ORIGINS: List[str] = [
        "http://localhost",
        "http://localhost:8080",
        "http://localhost:3000",
    ]

    # Domain wiring: REST path segment -> aspect name
    IFDD_ASPECTS: Dict[str, str] = {
        "products": "product",
        "functions": "function",
        "locations": "location",
        "organisations": "organisation",
    }

    # Graph traversal: predicate -> maximum traversal depth
    IFDD_GRAPH_PREDICATES: Dict[str, int] = {
        "hasPart": 1,
        "isPartOf": 1,
        "containsProduct": 1,
        "containedIn": 1,
        "providesFunction": 1,
        "implementedBy": 1,
        "usesFunction": 1,
        "usedBy": 1,
        "responsibleOrganisation": 1,
        "consumer": 1,
    }
    IFDD_GRAPH_MAX_DEPTH: int = 4

    # FastAPI
    DEBUG: bool = False
    FASTAPI_SECRET_KEY: str = "SECRET HERE"
    REQUEST_TIMEOUT: int = 60
    MAX_WORKERS: int = 4

    IFDD_BE_AUTH_ENABLED: bool = True
    IFDD_BE_SSL_ENABLED: bool = True

    # Database pool
    IFDD_DB_POOL_SIZE: int = 20
    IFDD_DB_MAX_OVERFLOW: int = 0
    IFDD_DB_POOL_TIMEOUT: int = 30

    @property
    def oidc_algorithms(self) -> List[str]:
        """The signature algorithms accepted for tokens, as PyJWT expects them."""
        return [self.IFDD_OIDC_JWKS_ALGORITHM]


_settings: Optional[CoreSettings] = None
_settings_class: Type[CoreSettings] = CoreSettings


def configure(settings: CoreSettings) -> CoreSettings:
    """Register the settings every part of ifdd.be.core will use.

    Args:
        settings: The settings of the instance, usually a subclass of
            :class:`CoreSettings`.

    Returns:
        The same settings object.
    """
    global _settings
    _settings = settings
    return _settings


def get_settings() -> CoreSettings:
    """Return the registered settings, creating defaults on first use.

    Returns:
        The settings passed to :func:`configure`, or a :class:`CoreSettings`
        read from the environment if none were registered.
    """
    global _settings
    if _settings is None:
        _settings = _settings_class()
    return _settings


def reset_settings() -> None:
    """Forget the registered settings; the next :func:`get_settings` reads them again.

    Meant for tests that need different settings per test.
    """
    global _settings
    _settings = None
