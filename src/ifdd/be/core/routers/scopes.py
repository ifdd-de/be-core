"""``/scopes``: the values of ``objScope`` in use."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Body, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request
from starlette.responses import Response

from .. import repository, schemas
from ..auth.oidc import nodes_read_auth
from ..contexts import Access
from ..db import get_db
from ..openapi import error_responses
from .params import aspect_id_param, end_param, order_param, start_param, valid_at

router = APIRouter(tags=["scopes"])

_RESPONSES = {
    200: {
        "description": "The distinct values; the header X-Total-Count has their number.",
        "content": {
            "application/json": {
                "example": [{"@id": "example", "search_scope": "example", "name": "example"}]
            }
        },
    },
    **error_responses(401, 403),
}


@router.get(
    "/scopes",
    response_model=list[schemas.Scope],
    summary="List the objScope values in use",
    responses=_RESPONSES,
)
@router.post(
    "/scopes",
    response_model=list[schemas.Scope],
    summary="List the objScope values in use (values in the body)",
    responses=_RESPONSES,
)
async def main_get_scopes(
    request: Request,
    response: Response,
    req_body: Optional[schemas.Ids] = Body(
        None, description="Optional: only these values (sent as `ids`)."
    ),
    aspect_id: Optional[str] = aspect_id_param(),
    start: int = start_param(),
    end: int = end_param(),
    order: str = order_param(),
    at: datetime = Depends(valid_at),
    token_data: dict = Depends(nodes_read_auth()),
    session: AsyncSession = Depends(get_db),
):
    """List every distinct `objScope` of the documents the client may read.

    `objScope` has no meaning for access; clients use it to tell sources or
    areas apart. Needs the node read role; values that occur only in domain
    contexts without a matching pattern are left out.
    \f
    ``start``, ``end`` and ``order`` are accepted for the list protocol of
    the UI but not applied: the answer is always complete.

    Returns:
        One entry per value, ``@id``, ``search_scope`` and ``name`` all the value.
    """
    id_list = None if req_body is None else req_body.ids
    scopes = await repository.distinct_field_values(
        session, at, Access.from_token(token_data), "objScope", aspect=aspect_id, values=id_list
    )
    ret_list = [
        {"@id": str(s), "search_scope": str(s), "name": str(s)} for s in scopes
    ]
    response.headers["Access-Control-Expose-Headers"] = "X-Total-Count"
    response.headers["X-Total-Count"] = str(len(ret_list))
    response.headers["Cache-Control"] = "max-age=3"
    return ret_list
