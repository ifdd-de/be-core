"""The c_* cache metadata of a JSON-LD document.

Every schema defines six terms with the prefix ``c_`` ("cache metadata"). The
backend never stores them inside the document: they are taken out of the
document before it is stored, their values live in table columns of the row
(see :mod:`ifdd.be.core.models`), and they are added to the document again
when it is read.

Two of them describe the stored copy and are always set by the backend; a
value sent by a client is discarded. The other four come from the source of
the document and are kept as sent:

=====================  =========  ===============================================
term                   origin     column
=====================  =========  ===============================================
``c_created``          source     ``src_created``
``c_modified``         source     ``src_modified``
``c_validNotBefore``   source     ``valid_period``, lower bound (valid time)
``c_validNotAfter``    source     ``valid_period``, upper bound (valid time)
``c_cacheCreated``     backend    ``cache_created``: first stored
``c_cacheUpdated``     backend    ``cache_updated``: this version stored
=====================  =========  ===============================================

Only these six names are known; any other ``c_*`` term is rejected.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from .helper import ensure_timezone_utc

CACHE_PREFIX = "c_"

SOURCE_TERMS = ("c_created", "c_modified", "c_validNotBefore", "c_validNotAfter")
BACKEND_TERMS = ("c_cacheCreated", "c_cacheUpdated")
CACHE_TERMS = SOURCE_TERMS + BACKEND_TERMS

XSD_DATETIME = "http://www.w3.org/2001/XMLSchema#dateTime"


class CacheMetaError(ValueError):
    """A document carries c_* metadata the backend cannot accept (HTTP 422)."""


@dataclass(frozen=True)
class SourceMeta:
    """The c_* values a source sent with a document; None means "not sent"."""

    created: Optional[datetime] = None
    modified: Optional[datetime] = None
    valid_not_before: Optional[datetime] = None
    valid_not_after: Optional[datetime] = None


def split_cache_meta(document: Mapping[str, Any]) -> tuple[dict, SourceMeta]:
    """Separate a compacted document from its c_* metadata.

    Returns a copy of the document without any c_* term and the source values
    it carried. Backend values (``c_cacheCreated``, ``c_cacheUpdated``) are
    dropped: the backend sets them itself. An unknown c_* term raises
    :class:`CacheMetaError`.
    """
    content: dict = {}
    sent: dict[str, datetime] = {}
    for term, value in document.items():
        if not term.startswith(CACHE_PREFIX):
            content[term] = value
        elif term in SOURCE_TERMS:
            sent[term] = _parse_datetime(term, value)
        elif term not in BACKEND_TERMS:
            raise CacheMetaError(
                f"unknown cache metadata term {term!r}; known: {', '.join(CACHE_TERMS)}"
            )
    meta = SourceMeta(
        created=sent.get("c_created"),
        modified=sent.get("c_modified"),
        valid_not_before=sent.get("c_validNotBefore"),
        valid_not_after=sent.get("c_validNotAfter"),
    )
    return content, meta


def cache_iris_in(expanded: Mapping[str, Any]) -> list[str]:
    """Property IRIs of an expanded document that name a c_* term.

    A client can bypass :func:`split_cache_meta` by writing a term as a
    compact IRI (``"product:c_created"``). Such properties must not reach the
    stored document either; the caller rejects them.
    """
    found = []
    for iri in expanded:
        local_name = iri.rstrip("/").rsplit("/", 1)[-1].rsplit("#", 1)[-1]
        if local_name in CACHE_TERMS:
            found.append(iri)
    return found


def stored_values(
    *,
    created: Optional[datetime],
    modified: Optional[datetime],
    valid_not_before: datetime,
    valid_not_after: Optional[datetime],
    cache_created: datetime,
    cache_updated: datetime,
) -> dict[str, datetime]:
    """The c_* values of a stored version, by term.

    Terms without a value are left out: an open-ended valid time has no
    ``c_validNotAfter``, an unsent ``c_created`` stays absent.
    """
    values = {
        "c_created": created,
        "c_modified": modified,
        "c_validNotBefore": valid_not_before,
        "c_validNotAfter": valid_not_after,
        "c_cacheCreated": cache_created,
        "c_cacheUpdated": cache_updated,
    }
    return {term: value for term, value in values.items() if value is not None}


def as_utc_text(value: datetime) -> str:
    """ISO 8601 in UTC, whatever time zone the database session uses."""
    return value.astimezone(timezone.utc).isoformat()


def add_to_compacted(document: dict, values: Mapping[str, datetime]) -> dict:
    """Add c_* values to a compacted document (plain terms, ISO 8601, UTC)."""
    for term, value in values.items():
        document[term] = as_utc_text(value)
    return document


def add_to_expanded(expanded: dict, values: Mapping[str, datetime], namespace: str) -> dict:
    """Add c_* values to an expanded document.

    ``namespace`` is the IRI of the schema namespace of the stored context,
    e.g. ``https://type/v1/product/``; the property IRI is namespace + term,
    exactly as the schema defines it (``product:c_created``).
    """
    for term, value in values.items():
        expanded[f"{namespace}{term}"] = [{"@type": XSD_DATETIME, "@value": as_utc_text(value)}]
    return expanded


def _parse_datetime(term: str, value: Any) -> datetime:
    """An xsd:dateTime value as sent: a string or a JSON-LD value object."""
    if isinstance(value, Mapping) and "@value" in value:
        value = value["@value"]
    if not isinstance(value, str):
        raise CacheMetaError(f"{term}: expected an ISO 8601 date-time, got {value!r}")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as err:
        raise CacheMetaError(f"{term}: not an ISO 8601 date-time: {value!r}") from err
    return ensure_timezone_utc(parsed)
