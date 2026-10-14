"""Parameters shared by several endpoints, with their OpenAPI descriptions.

Each function returns a fresh FastAPI parameter object, to be used as the
default value of an endpoint argument (``start: int = start_param()``). The
defaults are the values the endpoints had before they were documented; only
the descriptions are new.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import Path, Query

from ..helper import ensure_timezone_utc, utc_now
from ..repository import DEFAULT_SORT


def valid_at(
    at: Optional[datetime] = Query(
        None,
        description=(
            "Instant in valid time (ISO 8601). Returns the versions that are "
            "valid at this instant, as the backend knows them now. Without a "
            "time zone the value is read as UTC. Default: now."
        ),
        examples=["2026-06-01T12:00:00Z"],
    ),
) -> datetime:
    """The instant a read looks at, in UTC.

    Args:
        at: The query parameter ``at``; None means now.

    Returns:
        ``at`` with UTC as time zone if it had none, or the current time.
    """
    return ensure_timezone_utc(at) if at is not None else utc_now()


def segment() -> Any:
    """Path parameter ``node_aspect``: the REST segment of an aspect."""
    return Path(
        description="REST path segment of an aspect, e.g. `products` (configuration IFDD_ASPECTS).",
        examples=["products"],
    )


def document_id() -> Any:
    """Path parameter ``node_id``: the last path segment of an ``@id``."""
    return Path(
        description="Last path segment of the document's `@id`.",
        examples=["3f2b6c1e-0a4d-4f7e-9b1a-2c5d8e7f6a90"],
    )


def start_param() -> Any:
    """Query parameter ``start``: first entry of a page."""
    return Query(0, description="First entry of the page, 0-based.")


def end_param() -> Any:
    """Query parameter ``end``: entry after the last one of a page."""
    return Query(
        100,
        description="Entry after the last one of the page: `start=0&end=25` returns 25 entries.",
    )


def order_param() -> Any:
    """Query parameter ``order``: sort direction."""
    return Query(
        "ASC",
        description="Sort direction, `ASC` or `DESC`. Any other value keeps storage order.",
    )


def sort_param() -> Any:
    """Query parameter ``sort``: one of the indexed sort keys."""
    return Query(
        DEFAULT_SORT,
        description=(
            "Sort key: one of the six c_* terms or `objName`, `objType`, `objScope`. "
            "Every key has an index; any other key is refused with 422."
        ),
    )


def context_param() -> Any:
    """Query parameter ``context`` of the aspect lists."""
    return Query(
        None,
        description=(
            "Context URL to list instead of the aspect context, e.g. a domain context. "
            "403 if no context pattern of the client matches it, 422 if the backend "
            "does not accept it."
        ),
        examples=["https://schema/v1/breaker.grid.example.ifdd.de.jsonld"],
    )


def type_id_param() -> Any:
    """Query parameter ``type_id``: filter on ``objType``."""
    return Query(None, description="Only documents whose `objType` is this value.")


def scope_id_param() -> Any:
    """Query parameter ``scope_id``: filter on ``objScope``."""
    return Query(None, description="Only documents whose `objScope` is this value.")


def query_param() -> Any:
    """Query parameter ``query``: text search."""
    return Query(
        None,
        description="Only documents whose stored JSON contains this text (case-sensitive).",
    )


def aspect_id_param() -> Any:
    """Query parameter ``aspect_id`` of ``/types`` and ``/scopes``."""
    return Query(None, description="Only documents of this aspect, e.g. `product`.")
