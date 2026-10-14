"""Graph traversal for ``/graph_data``.

Starting from a document, the traversal follows the relations named in
``IFDD_GRAPH_PREDICATES`` through the base and aspect contexts and collects
nodes and edges; two converters turn them into the element format of
cytoscape.js, which the graph view of ifdd-ui draws.
"""

from datetime import datetime
from typing import Dict, List

from sqlalchemy.ext.asyncio import AsyncSession

from . import repository
from .config import get_settings


async def build_graph_data(
    session: AsyncSession,
    g_nodes: Dict[str, Dict[str, str]],
    g_edges: Dict[str, Dict[str, str]],
    obj_id: str,
    predicates: Dict[str, int],
    at: datetime,
):
    """Collect a document and the documents it relates to, recursively.

    Args:
        session: Database session.
        g_nodes: Collected nodes by ``@id``; filled in place.
        g_edges: Collected edges by ``"<source> # <predicate> # <target>"``;
            filled in place.
        obj_id: ``@id`` of the document to start from.
        predicates: Predicate to remaining depth. A predicate is followed
            while its depth is above 0 and below ``IFDD_GRAPH_MAX_DEPTH``;
            each step down lowers it by one.
        at: Instant in valid time.
    """
    # The compacted documents of the base and aspect contexts are merged
    # into one flat dict; domain contexts are left out (see repository).
    max_depth = get_settings().IFDD_GRAPH_MAX_DEPTH
    obj_list = await repository.generic_documents_with_id(session, at, obj_id)

    obj_dict: Dict[str, str] = {}
    for obj in obj_list:
        obj_dict.update(obj.json)
        obj_dict["aspect"] = obj.aspect

    obj_dict.pop("@context", None)
    if "@id" in obj_dict:
        g_nodes[obj_dict["@id"]] = obj_dict

    remaining = predicates.copy()
    for predicate, cnt in predicates.items():
        if not 0 < cnt < max_depth:
            remaining[predicate] = 0
            continue
        remaining[predicate] = cnt - 1
        if predicate not in obj_dict:
            continue
        value = obj_dict[predicate]
        if isinstance(value, str):
            targets = [value]
        elif isinstance(value, list):
            targets = value
        else:
            targets = []
        for target in targets:
            await build_graph_data(
                session, g_nodes, g_edges, target, remaining, at
            )
            g_edges[f"{obj_dict['@id']} # {predicate} # {target}"] = {
                "source": obj_dict["@id"],
                "target": target,
                "label": predicate,
            }


async def convert_cytoscape_nodes(
    g_nodes: Dict[str, Dict[str, str]],
    ret_list: List[Dict[str, str | Dict[str, str | int]]],
):
    """Append the collected nodes as cytoscape.js node elements.

    Args:
        g_nodes: Collected nodes by ``@id``.
        ret_list: The answer; filled in place. A node is labelled with its
            ``objName`` (its ``@id`` without one) and classed by its aspect.
    """
    for node_id, node in g_nodes.items():
        ret_list.append(
            {
                "data": {
                    "id": node_id,
                    "label": node.get("objName", node_id),
                    "url": node_id,
                    "class": node.get("aspect", ""),
                }
            }
        )


async def convert_cytoscape_edges(
    g_edges: Dict[str, Dict[str, str]],
    ret_list: List[Dict[str, str | Dict[str, str | int]]],
):
    """Append the collected edges as cytoscape.js edge elements.

    Args:
        g_edges: Collected edges.
        ret_list: The answer; filled in place. Every edge is labelled with
            its predicate.
    """
    for edge in g_edges.values():
        ret_list.append(
            {
                "data": {
                    "source": edge["source"],
                    "target": edge["target"],
                    "label": edge["label"],
                    "state": "active",
                }
            }
        )
