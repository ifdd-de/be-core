"""Stored rows as JSON-LD answers, with their c_* metadata added back."""

from __future__ import annotations

from typing import Iterable

from .cache_meta import add_to_compacted, add_to_expanded, stored_values
from .contexts import cache_namespace, name_of
from .jsonld import get_processor
from .models import Node


def cache_values(row: Node) -> dict:
    """The c_* values of a row, by term."""
    return stored_values(
        created=row.src_created,
        modified=row.src_modified,
        valid_not_before=row.valid_period.lower,
        valid_not_after=row.valid_period.upper,
        cache_created=row.cache_created,
        cache_updated=row.cache_updated,
    )


def list_entry(row: Node) -> dict:
    """A list entry: the stored compacted document plus its c_* terms.

    The stored context defines the c_* terms, so they are added as plain terms
    without any JSON-LD processing.
    """
    return add_to_compacted(dict(row.json), cache_values(row))


def merged_expanded(rows: Iterable[Node]) -> tuple[dict, dict[str, str]]:
    """One expanded document from all contexts of a node, and the namespaces by name.

    Each row gets its c_* values in the namespace of its own context first
    (``product:c_cacheUpdated`` next to ``location:c_cacheUpdated``), then the
    rows are merged. The namespace is the one the context gives its c_*
    terms, so nothing is assumed about prefixes or URL layout.
    """
    expanded: dict = {}
    namespaces: dict[str, str] = {}
    for row in rows:
        namespace = cache_namespace(row.context)
        namespaces[name_of(row.context)] = namespace
        expanded.update(add_to_expanded(dict(row.expanded), cache_values(row), namespace))
    return expanded, namespaces


def single_document(rows: Iterable[Node]) -> dict:
    """The answer of GET /{segment}/{id}: compacted with one prefix per context.

    The prefix of a context is its name (``product``,
    ``sub1.dom1.example``), and ``@context`` maps each name to its
    namespace, so any JSON-LD processor expands the answer again. Names are
    unique per node: the name is what access is decided on.
    """
    expanded, namespaces = merged_expanded(rows)
    compacted = get_processor().compact(expanded, namespaces, options={"graph": False})
    compacted["@context"] = namespaces
    return compacted
