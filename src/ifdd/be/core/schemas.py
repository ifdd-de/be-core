"""Request and response bodies with a fixed shape.

Documents themselves are free JSON-LD and stay plain ``dict``; only the
envelopes around them and the small helper answers have models here.
"""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class Node(BaseModel):
    """A stored document with its key fields (not used by the routers)."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    context: str
    aspect: str
    json_data: dict = Field(alias="json")


class NodeInp(BaseModel):
    """The body of PUT and PATCH: a JSON-LD document and its aspect."""

    model_config = ConfigDict(populate_by_name=True)

    json_data: dict = Field(
        alias="json",
        description=(
            "The JSON-LD document, compacted with one context: it carries `@id` (a URL "
            "whose path is the request path) and `@context` (one context URL below the "
            "schema URL of the instance), and may carry the c_* terms of the source."
        ),
    )
    aspect: str = Field(
        description=(
            "The aspect of the path segment, e.g. `product` for `/products/...` "
            "(configuration IFDD_ASPECTS)."
        )
    )


class Type(BaseModel):
    """One value of ``objType`` in use (``/types``)."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(alias="@id")
    search_type: str
    name: str


class Scope(BaseModel):
    """One value of ``objScope`` in use (``/scopes``)."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(alias="@id")
    search_scope: str
    name: str


class Ids(BaseModel):
    """A list of ``@id`` values that restricts a list or lookup."""

    ids: list[str] = Field(description="Full `@id` URLs of documents.")


class GraphRequest(BaseModel):
    """The start documents of a graph traversal (``/graph_data``)."""

    ids: list[str] = Field(description="Full `@id` URLs to start the traversal from.")


class WhoAmI(BaseModel):
    """What the backend reads from an access token (``/whoami``)."""

    preferred_username: Optional[str] = Field(
        description="The claim `preferred_username`; null if the token has none.",
        examples=["ifdd-demo"],
    )
    client_roles: list[str] = Field(
        description="Client roles of the backend client without a dot, sorted.",
        examples=[["ifdd_nodes_priv", "ifdd_nodes_ro", "ifdd_nodes_rw", "ifdd_public"]],
    )
    context_patterns: list[str] = Field(
        description=(
            "Client roles with a dot, lower-case and sorted: the context patterns that "
            "open domain contexts."
        ),
        examples=[["ifdd.de"]],
    )
