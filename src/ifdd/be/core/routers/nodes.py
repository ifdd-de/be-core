"""Single documents: GET, PUT, PATCH and DELETE on /{segment}/{id}, and /nodes/.

The routers only translate HTTP: the write logic lives in
:mod:`ifdd.be.core.writes`, the queries in :mod:`ifdd.be.core.repository`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from .. import presentation, repository, schemas, writes
from ..auth.oidc import nodes_read_auth, nodes_write_auth
from ..config import get_settings
from ..contexts import Access, ContextError, ContextForbidden, name_of
from ..db import get_db
from ..logging import setup_logger
from ..openapi import (
    DELETE_EXAMPLES,
    LIST_EXAMPLE,
    PATCH_EXAMPLES,
    PUT_EXAMPLES,
    SINGLE_DOCUMENT_EXAMPLE,
    error_responses,
    write_answer,
)
from .params import document_id, end_param, segment, start_param, valid_at

logger = setup_logger(__name__)

router = APIRouter(tags=["nodes"])

_ANSWERS = {
    writes.Outcome.CREATED: (status.HTTP_201_CREATED, "Node created successfully"),
    writes.Outcome.UPDATED: (status.HTTP_200_OK, "Node updated successfully"),
    writes.Outcome.UNCHANGED: (status.HTTP_200_OK, "No changes detected"),
    writes.Outcome.DELETED: (status.HTTP_200_OK, "Node deleted successfully"),
    writes.Outcome.NOT_FOUND: (status.HTTP_404_NOT_FOUND, "Node not found"),
}

def _answer(outcome: writes.Outcome) -> JSONResponse:
    code, message = _ANSWERS[outcome]
    return JSONResponse(status_code=code, content={"message": message})


def _path(request: Request) -> str:
    """The request path, decoded, as the @id paths are stored."""
    return request.scope["path"]


async def _write(call) -> JSONResponse:
    """Run a write and map rejected input to 422, a missing pattern to 403, a lost race to 409."""
    try:
        return _answer(await call)
    except ContextForbidden as err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(err)) from err
    except writes.WriteRejected as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(err)
        ) from err
    except IntegrityError as err:
        logger.warning(f"Write conflict: {err.orig}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Concurrent write, retry"
        ) from err


def _require_id_and_context(node_inp: schemas.NodeInp) -> Optional[JSONResponse]:
    """The 406 answer for a document without ``@id`` or ``@context``, else None."""
    if "@id" in node_inp.json_data and "@context" in node_inp.json_data:
        return None
    return JSONResponse(
        status_code=status.HTTP_406_NOT_ACCEPTABLE,
        content={"message": "@id or @context not found in data"},
    )


@router.get(
    "/nodes/",
    response_model=list[dict],
    summary="List documents of every aspect",
    responses={
        200: {
            "description": "One page of documents; the header X-Total-Count has the total.",
            "content": {"application/json": {"example": LIST_EXAMPLE}},
        },
        **error_responses(401, 403),
    },
)
async def list_all_nodes(
    response: Response,
    start: int = start_param(),
    end: int = end_param(),
    at: datetime = Depends(valid_at),
    token_data: dict = Depends(nodes_read_auth()),
    session: AsyncSession = Depends(get_db),
):
    """List the documents of all aspects and contexts the client may read.

    Every stored context of a document is its own entry. Needs the node read
    role; domain contexts without a matching context pattern are left out.
    \f
    Args:
        response: Carries the headers ``X-Total-Count`` and ``Cache-Control``.
        start: First entry of the page (0-based).
        end: Entry after the last one of the page.
        at: Instant in valid time.
        token_data: Claims of the access token.
        session: Database session.

    Returns:
        The page as list entries (:func:`~ifdd.be.core.presentation.list_entry`).
    """
    access = Access.from_token(token_data)
    total, rows = await repository.list_nodes(session, at, access, start=start, end=end)
    response.headers["Access-Control-Expose-Headers"] = "X-Total-Count"
    response.headers["X-Total-Count"] = str(total)
    response.headers["Cache-Control"] = "max-age=3"
    return [presentation.list_entry(row) for row in rows]


@router.get(
    "/{node_aspect}/{node_id}",
    summary="Read one document with all visible contexts",
    responses={
        200: {
            "description": (
                "The document, compacted with one prefix per context; `@context` maps "
                "each context name to its namespace."
            ),
            "content": {"application/json": {"example": SINGLE_DOCUMENT_EXAMPLE}},
        },
        **error_responses(401, 403, 404, 502),
    },
)
async def get_document(
    request: Request,
    node_aspect: str = segment(),
    node_id: str = document_id(),
    json_ld_expanded: Optional[str] = Header(
        None,
        alias="json-ld-expanded",
        description="`true`: answer in JSON-LD expanded form instead of the compacted one.",
    ),
    at: datetime = Depends(valid_at),
    token_data: dict = Depends(nodes_read_auth()),
    session: AsyncSession = Depends(get_db),
):
    """Read the document at this path, merged from every context the client may read.

    The prefix of each context is its name (`product`,
    `breaker.grid.example.ifdd.de`), and `@context` maps the names to their
    namespaces, so any JSON-LD processor expands the answer again. The c_*
    terms appear once per context.

    Needs the node read role. Domain contexts without a matching context
    pattern are left out; if none of the document's contexts is visible, the
    answer is 403 (not 404). 404 means there is no document at `at`.
    \f
    Args:
        request: The request; its path is the stored ``id_path``.
        node_aspect: Path segment (only documented; the path is used as a whole).
        node_id: Last path segment (only documented).
        json_ld_expanded: Header value; ``true`` asks for the expanded form.
        at: Instant in valid time.
        token_data: Claims of the access token.
        session: Database session.

    Returns:
        A JSON response with the compacted (or expanded) document.

    Raises:
        HTTPException: 404, 403, or 502 if a stored context no longer qualifies.
    """
    stored = await repository.documents_at_path(session, at, _path(request))
    if not stored:
        raise HTTPException(status_code=404, detail="Node not found")
    access = Access.from_token(token_data)
    rows = [row for row in stored if access.may_use(row.domain)]
    if not rows:
        raise HTTPException(
            status_code=403,
            detail="no context pattern of this client matches a context of this node: "
            + ", ".join(sorted({name_of(row.context) for row in stored})),
        )
    try:
        if str(json_ld_expanded or "").lower() == "true":
            expanded, _ = presentation.merged_expanded(rows)
            return JSONResponse(content=expanded)
        return JSONResponse(content=presentation.single_document(rows))
    except ContextError as err:
        # A stored context changed after the write and no longer qualifies.
        raise HTTPException(status_code=502, detail=str(err)) from err


_WRITE_RESPONSES = {
    200: {
        "description": "Updated, or unchanged (the existing versions are confirmed).",
        "content": write_answer("Node updated successfully"),
    },
    **error_responses(401, 403, 406, 409, 422, 502),
}


@router.put(
    "/{node_aspect}/{node_id}",
    summary="Write a document for a valid time",
    responses={
        201: {
            "description": "The document had no current version before.",
            "content": write_answer("Node created successfully"),
        },
        **_WRITE_RESPONSES,
    },
)
async def put_document(
    request: Request,
    node_inp: schemas.NodeInp = Body(openapi_examples=PUT_EXAMPLES),
    node_aspect: str = segment(),
    node_id: str = document_id(),
    token_data: dict = Depends(nodes_write_auth()),  # writes need the write role
    session: AsyncSession = Depends(get_db),
):
    """Write a whole document in one context for the valid time it names.

    The body is `{"json": <document>, "aspect": "<aspect>"}`. The path of
    the document's `@id` must be the request path, and `aspect` must belong
    to the first path segment.

    Valid time comes from `c_validNotBefore` / `c_validNotAfter` in the
    document (default: from now on). The write replaces only that part of
    the valid time and keeps the rest; it never shortens a validity (use
    DELETE for that). If the content is already known for the whole period,
    nothing new is stored: the answer is `No changes detected`, and the
    existing versions are confirmed (`c_cacheUpdated` moves to now).

    Needs the node write role, and a matching context pattern for a domain
    context (403 otherwise).
    \f
    Args:
        request: The request; its path must equal the path of ``@id``.
        node_inp: The body.
        node_aspect: Path segment (only documented).
        node_id: Last path segment (only documented).
        token_data: Claims of the access token.
        session: Database session.

    Returns:
        201, 200 (updated or unchanged) or 406, with a ``message``.
    """
    missing = _require_id_and_context(node_inp)
    if missing:
        return missing
    access = Access.from_token(token_data)
    return await _write(
        writes.put(session, node_inp.json_data, node_inp.aspect, _path(request), access)
    )


@router.patch(
    "/{node_aspect}/{node_id}",
    summary="Change some fields of a document",
    responses={
        **_WRITE_RESPONSES,
        **error_responses(404),
    },
)
async def patch_document(
    request: Request,
    node_inp: schemas.NodeInp = Body(openapi_examples=PATCH_EXAMPLES),
    node_aspect: str = segment(),
    node_id: str = document_id(),
    token_data: dict = Depends(nodes_write_auth()),
    session: AsyncSession = Depends(get_db),
):
    """Change some top-level fields of the version valid at the start of the named valid time.

    The fields sent replace those of the version valid at
    `c_validNotBefore` (default: now); the result is written like a PUT for
    the named valid time. 404 if there is no version at that instant. Same
    roles and checks as PUT.
    \f
    Args:
        request: The request; its path must equal the path of ``@id``.
        node_inp: The body; ``json`` holds ``@id``, ``@context`` and the changes.
        node_aspect: Path segment (only documented).
        node_id: Last path segment (only documented).
        token_data: Claims of the access token.
        session: Database session.

    Returns:
        200 (updated or unchanged), 404 or 406, with a ``message``.
    """
    missing = _require_id_and_context(node_inp)
    if missing:
        return missing
    access = Access.from_token(token_data)
    return await _write(
        writes.patch(session, node_inp.json_data, node_inp.aspect, _path(request), access)
    )


@router.delete(
    "/{node_aspect}/{node_id}",
    summary="End the validity of a document",
    responses={
        200: {"content": write_answer("Node deleted successfully")},
        **error_responses(401, 403, 404, 409, 422),
    },
)
async def delete_document(
    request: Request,
    node_aspect: str = segment(),
    node_id: str = document_id(),
    body: Optional[dict[str, Any]] = Body(
        None,
        description="Optional: c_validNotBefore / c_validNotAfter of the period to end.",
        openapi_examples=DELETE_EXAMPLES,
    ),
    context: Optional[str] = Query(
        None,
        description=(
            "Optional context URL: end only this context of the document. "
            "Without it the document ends in every context, and only if all "
            "of them may be written."
        ),
    ),
    token_data: dict = Depends(nodes_write_auth()),
    session: AsyncSession = Depends(get_db),
):
    """End the document for a period of valid time (default: from now on).

    The versions are not erased: they end in valid time, and with versioning
    the backend keeps the history in system time. Without `context` every
    context of the document ends, and only if the client may write all of
    them (403 otherwise; nothing is ended in part). With `context` only that
    context ends, e.g. a domain source withdrawing its values. 404 if
    nothing was valid in the period.
    \f
    Args:
        request: The request; its path selects the document.
        node_aspect: Path segment; must be a configured aspect (404 otherwise).
        node_id: Last path segment (only documented).
        body: Optional period.
        context: Optional context URL.
        token_data: Claims of the access token.
        session: Database session.

    Returns:
        200 or 404, with a ``message``.
    """
    aspect = get_settings().IFDD_ASPECTS.get(node_aspect)
    if aspect is None:
        raise HTTPException(status_code=404, detail="Unknown aspect")
    access = Access.from_token(token_data)
    return await _write(writes.delete(session, body, aspect, _path(request), access, context))
