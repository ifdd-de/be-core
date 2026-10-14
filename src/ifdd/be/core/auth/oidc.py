"""OIDC bearer-token validation.

Both the security scheme and the token cache are built on first use so that
importing this module never touches the settings.  This keeps import order
irrelevant for instances that register their own settings subclass.
"""

from __future__ import annotations

from functools import wraps
from typing import Annotated, Callable, List, Optional, Union

import jwt
from cachetools import TTLCache
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2AuthorizationCodeBearer
from jwt import PyJWKClient
from starlette.requests import Request

from ..config import get_settings
from ..logging import setup_logger

logger = setup_logger(__name__)

RoleSpec = Union[List[str], Callable[["object"], List[str]]]

# Value of the claim "typ" in Keycloak access tokens.
ACCESS_TOKEN_TYPE = "Bearer"


def _resolve_roles(spec: Optional[RoleSpec], settings) -> List[str]:
    """The role names of a role spec: a list, or a callable of the settings."""
    if spec is None:
        return []
    if callable(spec):
        return list(spec(settings))
    return list(spec)


_scheme: Optional[OAuth2AuthorizationCodeBearer] = None
_token_cache: Optional[TTLCache] = None


def get_oauth2_scheme() -> OAuth2AuthorizationCodeBearer:
    """The bearer-token extractor, built from the settings on first use.

    It reads ``Authorization: Bearer <token>``. With auth enabled a missing
    header answers 401; with auth off it returns None.
    """
    global _scheme
    if _scheme is None:
        settings = get_settings()
        _scheme = OAuth2AuthorizationCodeBearer(
            tokenUrl=settings.IFDD_OIDC_TOKEN_URL,
            authorizationUrl=settings.IFDD_OIDC_AUTHORIZATION_URL,
            refreshUrl=settings.IFDD_OIDC_REFRESH_URL,
            auto_error=settings.IFDD_BE_AUTH_ENABLED,
        )
    return _scheme


class _LazyOAuth2Scheme:
    """Dependency wrapper that defers scheme construction to request time."""

    async def __call__(self, request: Request) -> Optional[str]:
        """The bearer token of the request (see :func:`get_oauth2_scheme`)."""
        return await get_oauth2_scheme()(request)


oauth_2_scheme = _LazyOAuth2Scheme()


def _get_token_cache() -> TTLCache:
    """Validated tokens by their text.

    Holds ``IFDD_TOKEN_CACHE_SIZE`` entries for ``IFDD_TOKEN_CACHE_TTL`` seconds.
    """
    global _token_cache
    if _token_cache is None:
        settings = get_settings()
        _token_cache = TTLCache(
            maxsize=settings.IFDD_TOKEN_CACHE_SIZE, ttl=settings.IFDD_TOKEN_CACHE_TTL
        )
    return _token_cache


def ttl_cache(func):
    """Cache the result of an async token check per token text.

    A token is checked against the JWKS once and then served from the cache
    until the cache entry expires. The cache lifetime does not extend a
    token: an expired token in the cache is still answered from it until the
    entry ends, at most ``IFDD_TOKEN_CACHE_TTL`` seconds.
    """

    @wraps(func)
    async def wrapper(access_token, *args, **kwargs):
        """Answer from the cache, or check the token and remember the result."""
        cache = _get_token_cache()
        if access_token in cache:
            logger.debug("Token cache hit")
            return cache[access_token]
        result = await func(access_token, *args, **kwargs)
        cache[access_token] = result
        logger.debug("Token cache miss")
        return result

    return wrapper


_issuer_warning_logged = False


def _warn_once_without_issuer(settings) -> None:
    """Log once per process that the token issuer is not checked."""
    global _issuer_warning_logged
    if not settings.IFDD_OIDC_ISSUER and not _issuer_warning_logged:
        logger.warning("IFDD_OIDC_ISSUER is not set: the token issuer is not checked")
        _issuer_warning_logged = True


@ttl_cache
async def valid_access_token(access_token: Annotated[str, Depends(oauth_2_scheme)]):
    """Validate an access token and return its claims.

    Checks the signature against the realm's JWKS, the expiry, the audience
    ``IFDD_OIDC_JWKS_AUDIENCE``, the issuer ``IFDD_OIDC_ISSUER`` (if set)
    and that ``typ`` is ``Bearer`` (RFC 9068: ID tokens are refused).

    Args:
        access_token: The bearer token of the request.

    Returns:
        The decoded claims.

    Raises:
        HTTPException: 401 with the reason for any failed check.
    """
    settings = get_settings()
    jwks_client = PyJWKClient(
        settings.IFDD_OIDC_JWKS_URL, headers={"User-agent": "custom-user-agent"}
    )

    _warn_once_without_issuer(settings)

    try:
        signing_key = jwks_client.get_signing_key_from_jwt(access_token)
        claims = jwt.decode(
            access_token,
            signing_key.key,
            algorithms=settings.oidc_algorithms,
            audience=settings.IFDD_OIDC_JWKS_AUDIENCE,
            issuer=settings.IFDD_OIDC_ISSUER or None,
            options={"verify_exp": True},
        )
    except jwt.exceptions.PyJWKClientError as e:
        logger.info(f"JWKS client error: {e}")
        raise HTTPException(
            status_code=401,
            detail=f"Token validation failed: Unable to verify token signature. {e}",
        )
    except jwt.exceptions.ExpiredSignatureError as e:
        logger.info(f"Token expired: {e}")
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.exceptions.InvalidAudienceError as e:
        logger.info(f"Invalid audience: {e}")
        raise HTTPException(
            status_code=401,
            detail=f"Invalid token audience. Expected: {settings.IFDD_OIDC_JWKS_AUDIENCE}",
        )
    except jwt.exceptions.InvalidTokenError as e:
        logger.info(f"Invalid token error: {e}")
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")
    except Exception as e:
        logger.info(f"Unexpected error during token validation: {e}")
        raise HTTPException(status_code=401, detail=f"Authentication failed: {e}")

    # An ID token of the same client has the same audience and signature;
    # only the token type tells them apart (Keycloak: "Bearer" vs. "ID").
    # RFC 9068, section 5: resource servers must not accept ID tokens.
    if claims.get("typ") != ACCESS_TOKEN_TYPE:
        logger.info(f"Rejected token of type {claims.get('typ')!r}")
        raise HTTPException(status_code=401, detail="Invalid token: not an access token")
    return claims


def require_roles(required_roles: List[str]):
    """A dependency that needs a valid token with all of ``required_roles``.

    Unlike :func:`optional_auth` it has no development stand-in; the routers
    of the core use :func:`optional_auth` and its shortcuts.

    Args:
        required_roles: Client roles of ``IFDD_OIDC_JWKS_AUDIENCE``.

    Returns:
        The dependency; it answers 403 if a role is missing.
    """

    async def role_checker(token_data: dict = Depends(valid_access_token)):
        """Return the claims, or answer 403 if a required role is missing."""
        settings = get_settings()
        client_id = settings.IFDD_OIDC_JWKS_AUDIENCE
        resource_access = token_data.get("resource_access", {})
        user_roles = resource_access.get(client_id, {}).get("roles", [])
        for role in required_roles:
            if role not in user_roles:
                raise HTTPException(
                    status_code=403,
                    detail=f"Insufficient permissions. Role {role} required.",
                )
        return token_data

    return role_checker


def optional_auth(required_roles: Optional[RoleSpec] = None):
    """Return an auth dependency, or a development stand-in when auth is off.

    ``required_roles`` may be a plain list or a callable that receives the
    active settings and returns the list.  The callable form keeps role names
    that live in the configuration out of import-time evaluation.
    """

    async def dispatcher(request: Request):
        """Return the claims of the token, or the development user when auth is off."""
        settings = get_settings()
        if not settings.IFDD_BE_AUTH_ENABLED:
            return {
                "preferred_username": "dev-user",
                "resource_access": {
                    settings.IFDD_OIDC_JWKS_AUDIENCE: {
                        "roles": [
                            settings.IFDD_ROLE_PUBLIC,
                            settings.IFDD_ROLE_NODES_READ,
                            settings.IFDD_ROLE_NODES_WRITE,
                            # a context pattern: every domain context below the root
                            settings.IFDD_CONTEXT_ROOT,
                        ]
                    }
                },
            }
        roles = _resolve_roles(required_roles, settings)
        token = await oauth_2_scheme(request)
        token_data = await valid_access_token(token)
        client_id = settings.IFDD_OIDC_JWKS_AUDIENCE
        user_roles = (
            token_data.get("resource_access", {}).get(client_id, {}).get("roles", [])
        )
        for role in roles:
            if role not in user_roles:
                raise HTTPException(
                    status_code=403,
                    detail=f"Insufficient permissions. Role {role} required.",
                )
        return token_data

    return dispatcher


def nodes_read_auth():
    """Auth dependency requiring the configured node read role."""
    return optional_auth(lambda settings: [settings.IFDD_ROLE_NODES_READ])


def nodes_write_auth():
    """Auth dependency requiring the configured node write role."""
    return optional_auth(lambda settings: [settings.IFDD_ROLE_NODES_WRITE])


def public_auth():
    """Auth dependency requiring only a sign-in (the configured public role)."""
    return optional_auth(lambda settings: [settings.IFDD_ROLE_PUBLIC])
