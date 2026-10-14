"""The OpenAPI document of the backend: introduction, tags, errors, examples.

Everything here only *describes* the API; nothing changes how a request is
handled. The routers attach the pieces to their endpoints
(:func:`error_responses`, the example bodies), and :func:`build_openapi`
puts the document together: FastAPI's generated paths plus the
introduction, the tag descriptions, the license and the security schemes.

The text is written for people who call the API: what an endpoint does,
which role it needs, and when it answers 403 rather than 404. Notes for
developers stay in the code (after the form feed in an endpoint docstring,
which FastAPI cuts off).
"""

from __future__ import annotations

from typing import Any, Callable

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from .config import CoreSettings
from .version import __version__

REPOSITORY_URL = "https://github.com/ifdd-de/be-core"
OVERVIEW_URL = "https://github.com/ifdd-de/overview"

OAUTH2_SCHEME = "OAuth2AuthCode"
BEARER_SCHEME = "BearerToken"

# Example values used throughout the document. They follow the defaults of
# the IFDD templates (hosts rest and schema, the example domains grid and
# ops); a real instance has its own hosts.
EXAMPLE_SCHEMA_URL = "https://schema/v1"
EXAMPLE_ID = "https://rest/products/3f2b6c1e-0a4d-4f7e-9b1a-2c5d8e7f6a90"
EXAMPLE_PRODUCT_CONTEXT = f"{EXAMPLE_SCHEMA_URL}/product.jsonld"
EXAMPLE_DOMAIN_CONTEXT = f"{EXAMPLE_SCHEMA_URL}/breaker.grid.example.ifdd.de.jsonld"


TAGS: list[dict[str, str]] = [
    {
        "name": "aspects",
        "description": (
            "Lists of documents per aspect (`/products`, `/functions`, ...). The "
            "paths come from the configuration `IFDD_ASPECTS` of the instance. "
            "A list shows one entry per document in the aspect context, or in "
            "the context named with `context=`. Lists are paged with `start` "
            "and `end`; the header `X-Total-Count` tells the number of matches "
            "the client may see."
        ),
    },
    {
        "name": "nodes",
        "description": (
            "A single document at `/{segment}/{id}`: read it with all contexts "
            "the client may see, write it (PUT, PATCH) or end its validity "
            "(DELETE). Writes are bitemporal: they replace only the valid time "
            "they name and keep the rest."
        ),
    },
    {
        "name": "types",
        "description": "The values of `objType` in use, for filters in a client.",
    },
    {
        "name": "scopes",
        "description": "The values of `objScope` in use, for filters in a client.",
    },
    {
        "name": "graph",
        "description": (
            "Relations between documents as nodes and edges for a graph view "
            "(cytoscape.js format)."
        ),
    },
    {
        "name": "meta",
        "description": (
            "Version and sign-in checks: `/version` needs no token, "
            "`/prot_version` needs a sign-in (the UI shows its answer), "
            "`/whoami` shows what the backend reads from your token."
        ),
    },
]


def description(settings: CoreSettings) -> str:
    """The introduction at the top of the OpenAPI document (Markdown).

    Args:
        settings: The active settings; the text names the configured aspects,
            the schema URL and the role names of this instance.

    Returns:
        Markdown text for ``info.description``.
    """
    aspects = ", ".join(
        f"`/{segment}` ({aspect})" for segment, aspect in settings.IFDD_ASPECTS.items()
    )
    auth = (
        "Every endpoint except `/version` needs an OIDC **access token** of the realm "
        f"(`Authorization: Bearer ...`) whose audience is `{settings.IFDD_OIDC_JWKS_AUDIENCE}`. "
        "ID tokens are refused. Roles are client roles of that audience "
        f"(`resource_access.{settings.IFDD_OIDC_JWKS_AUDIENCE}.roles`)."
        if settings.IFDD_BE_AUTH_ENABLED
        else "**Authentication is switched off in this instance** (development mode): "
        "every request acts as a development user with all node roles and the "
        f"context pattern `{settings.IFDD_CONTEXT_ROOT}`."
    )
    return f"""\
The backend of an IFDD node stores JSON-LD documents of its domains and
answers with them. IFDD ("Integration of Federated Data Domains") keeps data
with the domains that own it and shares a published schema instead of a
common system; see [{OVERVIEW_URL}]({OVERVIEW_URL}).

This instance runs `ifdd-be-core` {__version__}.

## Documents and contexts

A document is identified by its `@id`, a URL of this backend
(`<backend URL>/<segment>/<id>`), and is stored once per JSON-LD context
(`@context`, a URL below `{settings.IFDD_SCHEMA_URL}`). The last path segment
of the context URL without `.jsonld` is the **context name**. There are three
kinds:

| Kind | Context names | Holds |
|---|---|---|
| base | `base` | overview fields such as `objType`, `objScope` |
| aspect | the aspects of this instance: {aspects} | the generic view of the aspect |
| domain | dotted names such as `breaker.grid.example.ifdd.de` | the fields of one domain |

Writes are sent as `{{"json": <document>, "aspect": "<aspect>"}}`; the
document carries its `@id` and one `@context` URL. Any other context name
is refused with 422.

## Access

{auth}

| Role | Allows |
|---|---|
| `{settings.IFDD_ROLE_PUBLIC}` | `/prot_version` (signed in, no data) |
| `{settings.IFDD_ROLE_NODES_READ}` | every read endpoint |
| `{settings.IFDD_ROLE_NODES_WRITE}` | PUT, PATCH, DELETE |

Base and aspect contexts need only these node roles. A **domain context**
also needs a **context pattern**: a client role with a dot, e.g.
`dom1.ifdd.de`, which matches the context of that name and every context
below it (`sub1.dom1.ifdd.de`, but not `xdom1.ifdd.de`). Lists leave out
domain contexts without a matching pattern; asking for one explicitly, or
writing to one, answers **403**, not 404. Use `/whoami` to see the roles
and patterns of your token.

## Time

Every stored version has a **valid time** (when it holds in the real world,
from `c_validNotBefore` / `c_validNotAfter`; default: from now on) and a
**system time** (when the backend knew it). Reads take an optional instant
`at` (ISO 8601, default now) and return what the backend knows now and is
valid at `at`. A write replaces only the valid time it names and keeps the
rest; an unchanged write creates no new version but *confirms* the existing
one (its `c_cacheUpdated` moves to the time of the write).

## Cache metadata

Six terms are never stored in the document, but added to every answer:
`c_created`, `c_modified`, `c_validNotBefore`, `c_validNotAfter` (sent by the
source) and `c_cacheCreated`, `c_cacheUpdated` (set by the backend; values
sent for them are ignored). All times are answered in UTC. Any other `c_*`
term is refused with 422.

## Errors

Errors are JSON objects with a `detail` field. Besides the codes listed per
endpoint, the proxy in front of the backend may answer 429 when a client
sends too many requests.
"""


def error_responses(*codes: int) -> dict[int | str, dict[str, Any]]:
    """The documented error answers for an endpoint.

    Args:
        *codes: HTTP status codes, each one of :data:`ERRORS`.

    Returns:
        A mapping for the ``responses`` argument of a FastAPI route.
    """
    return {code: ERRORS[code] for code in codes}


def _error(text: str, example: str) -> dict[str, Any]:
    return {
        "description": text,
        "content": {"application/json": {"example": {"detail": example}}},
    }


ERRORS: dict[int, dict[str, Any]] = {
    400: _error(
        "The database refused a value of the request.",
        "invalid input syntax for type timestamp with time zone",
    ),
    401: _error(
        "No access token, or the token is invalid, expired, not issued by the realm, "
        "for another audience, or an ID token.",
        "Not authenticated",
    ),
    403: _error(
        "The token lacks the role this endpoint needs, or no context pattern of the "
        "client matches the domain context involved.",
        "no context pattern of this client matches 'breaker.grid.example.ifdd.de'",
    ),
    404: _error("No current document at this path, or no such aspect.", "Node not found"),
    406: _error(
        "The document has no `@id` or no `@context`.",
        "@id or @context not found in data",
    ),
    409: _error(
        "Another write of the same document came in at the same moment. Send it again.",
        "Concurrent write, retry",
    ),
    422: _error(
        "The request cannot be applied: an unknown or foreign context, an `@id` that does "
        "not belong to the path, an unknown `c_*` term, an empty period, an unknown sort "
        "key, or a JSON-LD error. Validation errors of FastAPI also use this code.",
        "context name 'prodcut' is neither base, an aspect (function, location, "
        "organisation, product) nor a domain name (lower-case labels a-z, 0-9 and '-', "
        "separated by dots)",
    ),
    502: _error(
        "A JSON-LD context could not be fetched from the schema service; the detail "
        "names the URL and the cause.",
        "Dereferencing a URL did not result in a valid JSON-LD object. [...] "
        f"[loading remote context failed]; url: {EXAMPLE_PRODUCT_CONTEXT}; cause: 503 "
        f"Server Error: Service Unavailable for url: {EXAMPLE_PRODUCT_CONTEXT}",
    ),
}


# --- example bodies ------------------------------------------------------------------

PUT_EXAMPLES: dict[str, dict[str, Any]] = {
    "aspect": {
        "summary": "A product in its aspect context",
        "description": (
            "Valid from 2026-01-01 on; without c_validNotBefore it would be valid "
            "from now on."
        ),
        "value": {
            "aspect": "product",
            "json": {
                "@context": EXAMPLE_PRODUCT_CONTEXT,
                "@id": EXAMPLE_ID,
                "objName": "Breaker Q1",
                "objType": "breaker",
                "objScope": "example",
                "c_validNotBefore": "2026-01-01T00:00:00Z",
            },
        },
    },
    "domain": {
        "summary": "The same product in a domain context",
        "description": "Needs a context pattern matching breaker.grid.example.ifdd.de.",
        "value": {
            "aspect": "product",
            "json": {
                "@context": EXAMPLE_DOMAIN_CONTEXT,
                "@id": EXAMPLE_ID,
                "objName": "Breaker Q1",
                "serialNumber": "SN-4711",
                "manufacturer": "ACME",
                "yearOfManufacture": "2019",
                "operatingMechanism": "spring",
            },
        },
    },
}

PATCH_EXAMPLES: dict[str, dict[str, Any]] = {
    "rename": {
        "summary": "Change one field from now on",
        "value": {
            "aspect": "product",
            "json": {
                "@context": EXAMPLE_PRODUCT_CONTEXT,
                "@id": EXAMPLE_ID,
                "objName": "Breaker Q1 (renewed)",
            },
        },
    },
}

DELETE_EXAMPLES: dict[str, dict[str, Any]] = {
    "from_a_date": {
        "summary": "End the validity from a date on",
        "value": {"c_validNotBefore": "2027-01-01T00:00:00Z"},
    },
}

LIST_EXAMPLE: list[dict[str, Any]] = [
    {
        "@context": EXAMPLE_PRODUCT_CONTEXT,
        "@id": EXAMPLE_ID,
        "objName": "Breaker Q1",
        "objType": "breaker",
        "objScope": "example",
        "c_validNotBefore": "2026-01-01T00:00:00+00:00",
        "c_cacheCreated": "2026-10-13T08:15:02.512000+00:00",
        "c_cacheUpdated": "2026-10-13T08:15:02.512000+00:00",
    }
]

SINGLE_DOCUMENT_EXAMPLE: dict[str, Any] = {
    "@context": {
        "product": "https://type/v1/product/",
        "breaker.grid.example.ifdd.de": "https://type/v1/breaker.grid.example.ifdd.de/",
    },
    "@id": EXAMPLE_ID,
    "product:objName": "Breaker Q1",
    "product:objType": "breaker",
    "product:c_validNotBefore": "2026-01-01T00:00:00+00:00",
    "product:c_cacheUpdated": "2026-10-13T08:15:02.512000+00:00",
    "breaker.grid.example.ifdd.de:serialNumber": "SN-4711",
    "breaker.grid.example.ifdd.de:c_cacheUpdated": "2026-10-13T08:15:03.020000+00:00",
}


def write_answer(message: str) -> dict[str, Any]:
    """An example body of a successful write answer."""
    return {"application/json": {"example": {"message": message}}}


# --- the document --------------------------------------------------------------------


def build_openapi(app: FastAPI, settings: CoreSettings) -> Callable[[], dict[str, Any]]:
    """Return the function FastAPI calls for ``/openapi.json``.

    The document is built on the first call and kept.

    Args:
        app: The application whose routes are described.
        settings: The active settings.

    Returns:
        A function without arguments that returns the OpenAPI document.
    """

    def custom_openapi() -> dict[str, Any]:
        """Build the document on the first call, then return the kept one."""
        if app.openapi_schema:
            return app.openapi_schema

        openapi_schema = get_openapi(
            title=settings.API_TITLE,
            version=settings.IFDD_BE_VERSION,
            summary=settings.API_SUMMARY,
            description=description(settings),
            routes=app.routes,
            tags=TAGS,
            license_info={"name": "BSD-3-Clause", "identifier": "BSD-3-Clause"},
        )
        openapi_schema["externalDocs"] = {
            "description": "Source code and README of ifdd-be-core",
            "url": REPOSITORY_URL,
        }
        components = openapi_schema.setdefault("components", {})
        security_schemes = components.setdefault("securitySchemes", {})
        security_schemes[OAUTH2_SCHEME] = {
            "type": "oauth2",
            "description": (
                "Sign in at the realm with the authorization code flow and PKCE "
                f"(public client `{settings.IFDD_OIDC_JWKS_AUDIENCE}`). Used by "
                "\"Authorize\" in Swagger UI."
            ),
            "flows": {
                "authorizationCode": {
                    "authorizationUrl": settings.IFDD_OIDC_AUTHORIZATION_URL,
                    "tokenUrl": settings.IFDD_OIDC_TOKEN_URL,
                    "refreshUrl": settings.IFDD_OIDC_REFRESH_URL,
                    "scopes": {
                        "openid": "OpenID Connect",
                        "profile": "Profile information",
                        "email": "Email information",
                    },
                }
            },
        }
        security_schemes[BEARER_SCHEME] = {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": (
                "An access token obtained elsewhere, e.g. by a script with the "
                "client credentials grant. Paste the token without `Bearer `."
            ),
        }
        # GET and POST of the lists share one handler, which accepts an
        # optional {"ids": [...]} body. Browsers cannot send a body with GET
        # (fetch refuses it), so Swagger UI's "Try it out" sent nothing for a
        # GET with a documented body. The body stays documented for POST only;
        # the handler still accepts it either way.
        for path_item in openapi_schema.get("paths", {}).values():
            path_item.get("get", {}).pop("requestBody", None)

        if "security" not in openapi_schema and settings.IFDD_BE_AUTH_ENABLED:
            # Either scheme is enough (a list of alternatives).
            openapi_schema["security"] = [
                {OAUTH2_SCHEME: ["openid", "profile", "email"]},
                {BEARER_SCHEME: []},
            ]

        app.openapi_schema = openapi_schema
        return app.openapi_schema

    return custom_openapi
