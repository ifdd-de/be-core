"""Database access for nodes, written with the SQLAlchemy ORM.

Reads see the versions that are current in system time and valid at one
instant (:func:`visible_at`); every read index is partial on exactly that
"current" condition (see :mod:`ifdd.be.core.models`). Reads also see only the
contexts the client may read (:func:`readable_by`).

Writes carry out a :class:`~ifdd.be.core.temporal.WritePlan`. They serialise
per document with a transaction-level advisory lock, so two concurrent writes
of one document never see the same versions; the exclusion constraint of the
table is the safety net behind it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Optional, Sequence, get_args

from sqlalchemy import TIMESTAMP, ColumnElement, Text, and_, cast, func, literal, or_, select
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer

from .contexts import Access
from .models import SORTABLE_FIELDS, Node, document_field
from .temporal import Content, NewVersion, Period, Version, WritePlan

# --- reading ---------------------------------------------------------------------

# The keys a list may be sorted by: the c_* terms and a few document fields.
# Every one is backed by an index (see models), so a page sorted by it stops
# after the page. Any other key is refused (422) by the routers.
SortKey = Literal[
    "c_cacheUpdated",
    "c_cacheCreated",
    "c_created",
    "c_modified",
    "c_validNotBefore",
    "c_validNotAfter",
    "objName",
    "objType",
    "objScope",
]
SORT_COLUMNS: dict[str, ColumnElement[Any]] = {
    "c_cacheUpdated": Node.cache_updated,
    "c_cacheCreated": Node.cache_created,
    "c_created": Node.src_created,
    "c_modified": Node.src_modified,
    "c_validNotBefore": func.lower(Node.valid_period),
    "c_validNotAfter": func.upper(Node.valid_period),
    **{name: document_field(name) for name in SORTABLE_FIELDS},
}
DEFAULT_SORT: SortKey = "c_cacheUpdated"


def visible_at(at: datetime) -> ColumnElement[bool]:
    """Current in system time and valid at ``at``."""
    instant = literal(at, TIMESTAMP(timezone=True))
    return and_(Node.is_current, Node.valid_period.contains(instant))


def readable_by(access: Access) -> ColumnElement[bool]:
    """Base and aspect contexts, and the domain contexts a pattern matches."""
    conditions: list[ColumnElement[bool]] = [Node.domain.is_(None)]
    for pattern in access.patterns:
        conditions.append(Node.domain == pattern)
        conditions.append(Node.domain.endswith("." + pattern, autoescape=True))
    return or_(*conditions)


async def list_nodes(
    session: AsyncSession,
    at: datetime,
    access: Access,
    *,
    context: Optional[str] = None,
    aspect: Optional[str] = None,
    ids: Optional[Sequence[str]] = None,
    type_id: Optional[str] = None,
    scope_id: Optional[str] = None,
    search: Optional[str] = None,
    sort: SortKey = DEFAULT_SORT,
    order: str = "ASC",
    start: int = 0,
    end: int = 100,
) -> tuple[int, list[Node]]:
    """One page of documents and the total number of matches.

    The page is its own query, so an ORDER BY on an indexed column stops after
    the page (index scan + LIMIT). A window count in the same query would read
    and sort every match first: about five times slower for 20,000 current
    documents (PostgreSQL 18, measured). ``expanded`` is not loaded.
    """
    filters = [visible_at(at), readable_by(access)]
    if context:
        filters.append(Node.context == context)
    if aspect:
        filters.append(Node.aspect == aspect)
    if ids:
        filters.append(Node.id.in_(ids))
    # Containment (@>) is what the GIN index on json supports.
    if type_id:
        filters.append(Node.json.contains({"objType": type_id}))
    if scope_id:
        filters.append(Node.json.contains({"objScope": scope_id}))
    if search:
        filters.append(cast(Node.json, Text).contains(search, autoescape=True))

    page_size = max(end - start, 0)
    page = select(Node).where(*filters).order_by(*_ordering(sort, order))
    rows = list((await session.scalars(page.offset(start).limit(page_size))).all())
    if rows and len(rows) < page_size:
        return start + len(rows), rows  # the last page: its end is the total
    if not rows and start == 0:
        return 0, rows
    total = await session.scalar(select(func.count()).select_from(Node).where(*filters))
    return total or 0, rows


if set(get_args(SortKey)) != set(SORT_COLUMNS):
    raise RuntimeError("SortKey and SORT_COLUMNS must name the same keys")


def _ordering(sort: str, order: str) -> list[ColumnElement[Any]]:
    """ORDER BY for a sort key and direction; ``row_id`` breaks ties so pages are stable."""
    key = SORT_COLUMNS[sort]
    direction = order.lower()
    if direction == "asc":
        return [key.asc(), Node.row_id]
    if direction == "desc":
        return [key.desc(), Node.row_id.desc()]
    return [Node.row_id]  # stable pages without an explicit order


async def documents_at_path(session: AsyncSession, at: datetime, path: str) -> list[Node]:
    """All contexts of the document at a URL path, with ``expanded``.

    Not filtered by access: the caller tells "not found" from "forbidden".
    """
    query = (
        select(Node)
        .options(undefer(Node.expanded))
        .where(visible_at(at), Node.id_path == path)
        .order_by(Node.context)
    )
    return list((await session.scalars(query)).all())


async def generic_documents_with_id(
    session: AsyncSession, at: datetime, node_id: str
) -> list[Node]:
    """The base and aspect contexts of the document with an @id (graph traversal).

    Domain contexts are left out: the graph follows only the relations of
    IFDD_GRAPH_PREDICATES, and a domain term of the same plain name must not
    replace a generic value when the compacted documents are merged.
    """
    query = (
        select(Node)
        .where(visible_at(at), Node.id == node_id, Node.domain.is_(None))
        .order_by(Node.context)
    )
    return list((await session.scalars(query)).all())


async def distinct_field_values(
    session: AsyncSession,
    at: datetime,
    access: Access,
    field: str,
    *,
    aspect: Optional[str] = None,
    values: Optional[Sequence[str]] = None,
) -> list[Any]:
    """The distinct values of a document field, e.g. all objType in use."""
    column = Node.json[field]
    query = (
        select(column)
        .where(visible_at(at), readable_by(access), column.is_not(None))
        .group_by(column)
    )
    if aspect:
        query = query.where(Node.aspect == aspect)
    if values:
        query = query.where(Node.json[field].astext.in_(values))
    return list((await session.scalars(query)).all())


# --- writing ---------------------------------------------------------------------


@dataclass(frozen=True)
class DocumentKey:
    """Which document a write is about; the same for all its versions."""

    id: str
    id_path: str
    context: str
    aspect: str
    domain: Optional[str]  # name of a domain context, None for base and aspects


async def lock_document(session: AsyncSession, node_id: str, context: str) -> None:
    """Serialise writes of one document until the transaction ends."""
    key = func.hashtextextended(f"{node_id}\n{context}", 0)
    await session.execute(select(func.pg_advisory_xact_lock(key)))


async def database_now(session: AsyncSession) -> datetime:
    """The database clock, read after the lock: one clock for all workers."""
    return await session.scalar(select(func.clock_timestamp()))


async def current_versions(session: AsyncSession, node_id: str, context: str) -> list[Version]:
    """All versions of a document that are current in system time."""
    query = (
        select(Node)
        .options(undefer(Node.expanded))
        .where(Node.is_current, Node.id == node_id, Node.context == context)
        .order_by(Node.valid_period)
    )
    return [_as_version(row) for row in (await session.scalars(query)).all()]


async def current_keys_at_path(session: AsyncSession, path: str, aspect: str) -> list[DocumentKey]:
    """The documents (one per context) stored under a URL path."""
    query = (
        select(Node.id, Node.id_path, Node.context, Node.aspect, Node.domain)
        .where(Node.is_current, Node.id_path == path, Node.aspect == aspect)
        .distinct()
        .order_by(Node.context)
    )
    return [DocumentKey(*row) for row in (await session.execute(query)).all()]


async def apply_plan(
    session: AsyncSession,
    key: DocumentKey,
    plan: WritePlan,
    *,
    now: datetime,
    versioning: bool,
) -> None:
    """Retire and record versions as planned.

    With versioning, a retired version ends in system time at ``now`` and stays
    as history. Without, it is deleted: only current knowledge is kept.
    """
    for version in plan.retire:
        row: Node = version.row
        if versioning:
            row.sys_period = Range(row.sys_period.lower, now)
        else:
            await session.delete(row)
    # Retire first: the exclusion constraint checks every statement, and the
    # new versions overlap the retired ones until those are closed or gone.
    await session.flush()
    session.add_all(_new_row(key, version, now) for version in plan.record)
    await session.flush()


async def confirm(session: AsyncSession, versions: Sequence[Version], *, now: datetime) -> None:
    """Record that an unchanged write repeated these versions.

    Only ``cache_updated`` changes, in place: no new version, with or without
    versioning, because nothing the document says has changed.
    """
    for version in versions:
        row: Node = version.row
        row.cache_updated = now
    await session.flush()


def canonical(expanded: dict) -> str:
    """The comparison form of an expanded document."""
    return json.dumps(expanded, sort_keys=True, separators=(",", ":"))


def _as_version(row: Node) -> Version:
    content = Content(
        canonical=canonical(row.expanded),
        created=row.src_created,
        modified=row.src_modified,
        document=row.json,
        expanded=row.expanded,
    )
    valid = Period(row.valid_period.lower, row.valid_period.upper)
    return Version(valid=valid, content=content, cache_created=row.cache_created, row=row)


def _new_row(key: DocumentKey, version: NewVersion, now: datetime) -> Node:
    return Node(
        id=key.id,
        id_path=key.id_path,
        context=key.context,
        aspect=key.aspect,
        domain=key.domain,
        sys_period=Range(now, None),
        valid_period=Range(version.valid.start, version.valid.end),
        src_created=version.content.created,
        src_modified=version.content.modified,
        cache_created=version.cache_created,
        cache_updated=now,
        json=version.content.document,
        expanded=version.content.expanded,
    )
