"""OIDC access-token validation and the role checks used as FastAPI dependencies."""

from .oidc import (
    get_oauth2_scheme,
    nodes_read_auth,
    nodes_write_auth,
    optional_auth,
    public_auth,
    require_roles,
    valid_access_token,
)

__all__ = [
    "get_oauth2_scheme",
    "nodes_read_auth",
    "nodes_write_auth",
    "optional_auth",
    "public_auth",
    "require_roles",
    "valid_access_token",
]
