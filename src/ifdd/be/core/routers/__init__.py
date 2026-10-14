"""The generic routers of the backend; :func:`ifdd.be.core.create_app` includes them."""

from .aspects import build_aspect_router
from .graph_data import router as graph_data_router
from .nodes import router as nodes_router
from .scopes import router as scopes_router
from .node_types import router as types_router
from .versions import router as versions_router

__all__ = [
    "build_aspect_router",
    "graph_data_router",
    "nodes_router",
    "scopes_router",
    "types_router",
    "versions_router",
]
