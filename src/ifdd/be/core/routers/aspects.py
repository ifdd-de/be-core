"""Aspect routes, generated from configuration.

The original template hard-coded one stacked decorator block per aspect
(products, functions, locations, organisations).  Here the same routes are
registered from the IFDD_ASPECTS mapping, so an instance adds or renames an
aspect through its .env rather than through a code change.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request
from starlette.responses import Response

from .. import presentation, repository, schemas
from ..auth.oidc import nodes_read_auth
from ..config import get_settings
from ..contexts import Access, ContextError
from ..contexts import parse as parse_context
from ..db import get_db
from ..logging import setup_logger
from ..openapi import LIST_EXAMPLE, error_responses
from .params import (
    context_param,
    end_param,
    order_param,
    query_param,
    scope_id_param,
    sort_param,
    start_param,
    type_id_param,
    valid_at,
)

logger = setup_logger(__name__)


_SUMMARIES = {
    "GET": "List the documents of an aspect",
    "POST": "List the documents of an aspect (ids in the body)",
    "OPTIONS": "List the documents of an aspect (OPTIONS)",
}


def build_aspect_router(aspects: Optional[Dict[str, str]] = None) -> APIRouter:
    """Build a router exposing one collection endpoint per configured aspect.

    Args:
        aspects: REST path segment to aspect name; default ``IFDD_ASPECTS``.

    Returns:
        A router with GET, POST and OPTIONS on ``/<segment>`` for every aspect.
    """
    if aspects is None:
        aspects = get_settings().IFDD_ASPECTS
    router = APIRouter(tags=["aspects"])

    async def collection_endpoint(
        request: Request,
        response: Response,
        req_body: Optional[schemas.Ids] = Body(
            None,
            description="Optional: only these documents (`@id` URLs). Clients send it with POST.",
        ),
        type_id: Optional[str] = type_id_param(),
        scope_id: Optional[str] = scope_id_param(),
        query: Optional[str] = query_param(),
        start: int = start_param(),
        end: int = end_param(),
        order: str = order_param(),
        sort: repository.SortKey = sort_param(),
        context: Optional[str] = context_param(),
        at: datetime = Depends(valid_at),
        token_data: dict = Depends(nodes_read_auth()),
        session: AsyncSession = Depends(get_db),
    ):
        """List the documents of this aspect, one entry per document, one page at a time.

        By default the list shows the aspect context of each document. With
        `context=` it shows the documents stored in that context instead, for
        example a domain context; the client then needs a matching context
        pattern (403 otherwise). The header `X-Total-Count` has the number of
        matches the client may see.

        Every entry is the stored compacted document of that context plus its
        c_* terms. Needs the node read role.
        \f
        GET, POST and OPTIONS share this handler; ifdd-ui (react-admin) sends
        id lists with POST. The aspect is taken from the request path, so one
        function serves every configured segment.

        Returns:
            The page as list entries; 404 for a segment that is not configured.
        """
        settings = get_settings()
        path_segment = request.scope["path"].strip("/")
        aspect = settings.IFDD_ASPECTS.get(path_segment)
        if aspect is None:
            raise HTTPException(status_code=404, detail="Unknown aspect")
        access = Access.from_token(token_data)
        if context is None:
            context = f"{settings.IFDD_SCHEMA_URL}/{aspect}.jsonld"
        else:
            # An explicitly requested context must be accepted and readable.
            try:
                requested = parse_context(context)
            except ContextError as err:
                raise HTTPException(status_code=422, detail=str(err)) from err
            if not access.may_use(requested.domain_name):
                raise HTTPException(
                    status_code=403,
                    detail=f"no context pattern of this client matches {requested.name!r}",
                )

        total, rows = await repository.list_nodes(
            session,
            at,
            access,
            context=context,
            aspect=aspect,
            ids=None if req_body is None else req_body.ids,
            type_id=type_id,
            scope_id=scope_id,
            search=query,
            sort=sort,
            order=order,
            start=start,
            end=end,
        )
        response.headers["Access-Control-Expose-Headers"] = "X-Total-Count"
        response.headers["X-Total-Count"] = str(total)
        response.headers["Cache-Control"] = "max-age=3"
        return [presentation.list_entry(row) for row in rows]

    for path_segment, aspect in aspects.items():
        logger.debug(f"Registering aspect route /{path_segment} -> {aspect}")
        for method in ("GET", "POST", "OPTIONS"):
            # One route per method keeps the generated OpenAPI operation ids
            # unique; a single multi-method route reuses one id for all of them.
            router.add_api_route(
                f"/{path_segment}",
                collection_endpoint,
                methods=[method],
                response_model=list[dict],
                name=f"aspect_{aspect}_{method.lower()}",
                summary=f"{_SUMMARIES[method]}: {aspect}",
                responses={
                    200: {
                        "description": (
                            "One page of documents; the header X-Total-Count has the total."
                        ),
                        "content": {"application/json": {"example": LIST_EXAMPLE}},
                    },
                    **error_responses(401, 403, 404, 422, 502),
                },
            )

    return router
