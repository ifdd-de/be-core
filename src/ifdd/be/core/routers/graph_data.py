"""``/graph_data``: relations between documents for a graph view."""

from datetime import datetime
from typing import Dict, List

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from .. import schemas
from ..auth.oidc import nodes_read_auth
from ..config import get_settings
from ..db import get_db
from ..graph import build_graph_data, convert_cytoscape_edges, convert_cytoscape_nodes
from ..openapi import EXAMPLE_ID, error_responses
from .params import valid_at

router = APIRouter(tags=["graph"])

_EXAMPLE = [
    {
        "data": {
            "id": EXAMPLE_ID,
            "label": "Breaker Q1",
            "url": EXAMPLE_ID,
            "class": "product",
        }
    },
    {
        "data": {
            "id": "https://rest/locations/substation-a",
            "label": "Substation A",
            "url": "https://rest/locations/substation-a",
            "class": "location",
        }
    },
    {
        "data": {
            "source": EXAMPLE_ID,
            "target": "https://rest/locations/substation-a",
            "label": "containedIn",
            "state": "active",
        }
    },
]


@router.post(
    "/graph_data",
    response_model=List[Dict[str, str | Dict[str, str | int]]],
    summary="Relations of documents as graph nodes and edges",
    responses={
        200: {
            "description": "Nodes and edges in the element format of cytoscape.js.",
            "content": {"application/json": {"example": _EXAMPLE}},
        },
        **error_responses(401, 403),
    },
)
async def graph_data(
    request: Request,
    req_body: schemas.GraphRequest,
    at: datetime = Depends(valid_at),
    token_data: dict = Depends(nodes_read_auth()),
    session: AsyncSession = Depends(get_db),
):
    """Follow the relations of the given documents and return them as a graph.

    The traversal starts at every `@id` of the body and follows the
    predicates configured in `IFDD_GRAPH_PREDICATES` (e.g. `hasPart`,
    `containedIn`), each up to its configured depth; a predicate whose depth
    is not below `IFDD_GRAPH_MAX_DEPTH` is not followed. Only base and aspect
    contexts are read; domain contexts are never part of the graph. Nodes are
    labelled with their `objName` (or their `@id` if they have none).

    Needs the node read role.
    \f
    Args:
        request: The request.
        req_body: The start documents.
        at: Instant in valid time.
        token_data: Claims of the access token (role check only).
        session: Database session.

    Returns:
        cytoscape.js elements: first the nodes, then the edges.
    """
    return_val: List[Dict[str, str | Dict[str, str | int]]] = []
    predicates = dict(get_settings().IFDD_GRAPH_PREDICATES)

    g_nodes: Dict[str, Dict[str, str]] = {}
    g_edges: Dict[str, Dict[str, str]] = {}
    for node_id in req_body.ids:
        await build_graph_data(
            session, g_nodes, g_edges, node_id, predicates, at
        )
    await convert_cytoscape_nodes(g_nodes, return_val)
    await convert_cytoscape_edges(g_edges, return_val)
    return return_val
