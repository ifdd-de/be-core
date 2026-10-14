"""Version and sign-in checks: ``/version``, ``/prot_version``, ``/whoami``.

``/version`` is the endpoint for checks without a token. ``/prot_version``
is shown by ifdd-ui on its dashboard; its path, role and answer must stay as
they are. ``/whoami`` helps to find out why a request gets 403: it shows the
roles and context patterns the backend reads from the token.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from .. import schemas
from ..auth.oidc import optional_auth, public_auth
from ..config import get_settings
from ..contexts import Access
from ..openapi import error_responses

router = APIRouter(tags=["meta"])


@router.get(
    "/version",
    response_model=dict,
    summary="Version of the instance (no token needed)",
    responses={
        200: {"content": {"application/json": {"example": {"version": "26.10.2"}}}}
    },
    # Open to everyone: overrides the document-wide security requirement.
    openapi_extra={"security": []},
)
async def version():
    """Return the version of this backend instance.

    Needs no token, so it suits health checks and tests of the route through
    the proxy. The value is `IFDD_BE_VERSION` of the instance.
    \f
    Returns:
        ``{"version": IFDD_BE_VERSION}``.
    """
    return {"version": get_settings().IFDD_BE_VERSION}


@router.get(
    "/prot_version",
    response_model=dict,
    summary="Version of the instance (sign-in needed)",
    responses={
        200: {"content": {"application/json": {"example": {"version": "26.10.2_prot"}}}},
        **error_responses(401, 403),
    },
)
async def prot_version(
    token_data: dict = Depends(public_auth()),  # signed in, no further rights
):
    """Return the version of this backend instance with the suffix `_prot`.

    Needs a valid access token with the role `ifdd_public` (any signed-in
    user has it), but no permission on data. ifdd-ui shows this answer on
    its dashboard, which tells at a glance whether the login reaches the
    backend.
    \f
    The role name is ``IFDD_ROLE_PUBLIC``. Path, role and answer are an
    interface of ifdd-ui (``src/Dashboard.jsx``); keep them stable.

    Returns:
        ``{"version": IFDD_BE_VERSION + "_prot"}``.
    """
    return {"version": f"{get_settings().IFDD_BE_VERSION}_prot"}


@router.get(
    "/whoami",
    response_model=schemas.WhoAmI,
    summary="Who the backend thinks you are",
    responses=error_responses(401),
)
async def whoami(token_data: dict = Depends(optional_auth())):
    """Show the user name, client roles and context patterns of your token.

    Needs a valid access token, but no role. Use it when a request answers
    403: the answer lists exactly what the backend reads from the token.

    * `client_roles` are the roles without a dot, e.g. `ifdd_nodes_ro`.
    * `context_patterns` are the roles with a dot; each one opens the domain
      context of that name and every context below it.

    In development mode (authentication switched off) the answer shows the
    fixed development user.
    \f
    Roles are read from ``resource_access.<IFDD_OIDC_JWKS_AUDIENCE>.roles``;
    the split into patterns is the one :class:`~ifdd.be.core.contexts.Access`
    uses for every data request. Both lists are sorted.

    Args:
        token_data: The claims of the validated access token.

    Returns:
        A :class:`~ifdd.be.core.schemas.WhoAmI`.
    """
    audience = get_settings().IFDD_OIDC_JWKS_AUDIENCE
    roles = token_data.get("resource_access", {}).get(audience, {}).get("roles", [])
    return schemas.WhoAmI(
        preferred_username=token_data.get("preferred_username"),
        client_roles=sorted({role for role in roles if "." not in role}),
        context_patterns=list(Access.from_token(token_data).patterns),
    )
