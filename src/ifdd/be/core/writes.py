"""PUT, PATCH and DELETE of documents.

Each write runs the same steps:

1. check that the document belongs to the URL it is written to, that its
   context is accepted and that the client may write it
   (:mod:`ifdd.be.core.contexts`);
2. take the c_* metadata out of the document (:mod:`ifdd.be.core.cache_meta`);
3. lock the document, read the database clock and the current versions;
4. plan the change (:mod:`ifdd.be.core.temporal`) and carry it out
   (:mod:`ifdd.be.core.repository`). An unchanged write still confirms the
   versions it repeated: their ``c_cacheUpdated`` becomes the time of the
   write, so ``ifdd-be-purge`` does not end what a source keeps sending.

The functions return a :class:`Outcome`; the routers turn it into an HTTP
answer. Invalid input raises :class:`WriteRejected` (HTTP 422), a domain
context without a matching pattern :class:`~ifdd.be.core.contexts.ContextForbidden`
(HTTP 403).
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any, Mapping, Optional
from urllib.parse import unquote, urlparse

from sqlalchemy.ext.asyncio import AsyncSession

from . import repository
from .cache_meta import CacheMetaError, SourceMeta, cache_iris_in, split_cache_meta
from .config import get_settings
from .contexts import Access, ContextError, cache_namespace
from .contexts import parse as parse_context
from .jsonld import get_processor
from .repository import DocumentKey
from .temporal import (
    Content,
    Period,
    PeriodError,
    plan_delete,
    plan_put,
    requested_period,
    version_at,
)


class Outcome(enum.Enum):
    """The result of a write; the routers map it to the HTTP answer."""

    CREATED = "created"  # the document had no current version before
    UPDATED = "updated"
    UNCHANGED = "unchanged"  # everything written was already known
    DELETED = "deleted"
    NOT_FOUND = "not found"


class WriteRejected(ValueError):
    """The request cannot be applied as sent (HTTP 422)."""


async def put(
    session: AsyncSession, document: Mapping[str, Any], aspect: str, path: str, access: Access
) -> Outcome:
    """Write a whole document for the valid time it names (default: from now)."""
    key = document_key(document, aspect, path, access)
    body, meta = _split(document)
    content = _content(body, meta)

    await repository.lock_document(session, key.id, key.context)
    now = await repository.database_now(session)
    current = await repository.current_versions(session, key.id, key.context)
    valid = _period(meta, now)

    plan = plan_put(current, content, valid, now)
    if not plan.changes_anything:
        await repository.confirm(session, plan.confirm, now=now)
        return Outcome.UNCHANGED
    await repository.apply_plan(session, key, plan, now=now, versioning=_versioning())
    return Outcome.UPDATED if current else Outcome.CREATED


async def patch(
    session: AsyncSession, document: Mapping[str, Any], aspect: str, path: str, access: Access
) -> Outcome:
    """Change some fields of the version valid at the start of the named valid time.

    The fields sent replace those of that version (top level only); the result
    is written like a PUT for the named valid time (default: from now).
    """
    key = document_key(document, aspect, path, access)
    changes, meta = _split(document)

    await repository.lock_document(session, key.id, key.context)
    now = await repository.database_now(session)
    current = await repository.current_versions(session, key.id, key.context)
    valid = _period(meta, now)

    base = version_at(current, valid.start)
    if base is None:
        return Outcome.NOT_FOUND
    merged = SourceMeta(
        created=meta.created or base.content.created,
        modified=meta.modified or base.content.modified,
    )
    content = _content({**base.content.document, **changes}, merged)

    plan = plan_put(current, content, valid, now)
    if not plan.changes_anything:
        await repository.confirm(session, plan.confirm, now=now)
        return Outcome.UNCHANGED
    await repository.apply_plan(session, key, plan, now=now, versioning=_versioning())
    return Outcome.UPDATED


async def delete(
    session: AsyncSession,
    body: Optional[Mapping[str, Any]],
    aspect: str,
    path: str,
    access: Access,
    context: Optional[str] = None,
) -> Outcome:
    """End the document for the named valid time (default: from now).

    Without ``context`` the document ends in every context, and only if the
    client may write all of them: nothing is ended in part. With ``context``
    (a context URL) only that context ends, e.g. a domain source withdrawing
    its values. The body is optional and may only carry ``c_validNotBefore``
    and ``c_validNotAfter``.
    """
    leftover, meta = _split(body or {})
    if leftover:
        raise WriteRejected(
            "DELETE accepts only c_validNotBefore and c_validNotAfter, got: "
            + ", ".join(sorted(leftover))
        )
    keys = await repository.current_keys_at_path(session, path, aspect)
    if context is not None:
        _parse(context)
        keys = [key for key in keys if key.context == context]
    for key in keys:
        access.require(key.domain)
    deleted = False
    for key in keys:
        await repository.lock_document(session, key.id, key.context)
        now = await repository.database_now(session)
        current = await repository.current_versions(session, key.id, key.context)
        plan = plan_delete(current, _period(meta, now))
        if plan.changes_anything:
            await repository.apply_plan(session, key, plan, now=now, versioning=_versioning())
            deleted = True
    return Outcome.DELETED if deleted else Outcome.NOT_FOUND


def document_key(
    document: Mapping[str, Any], aspect: str, path: str, access: Access
) -> DocumentKey:
    """The document a write is about, checked against the URL it is sent to.

    The path of the ``@id`` must be the request path (the host is not
    compared: it is operational, see the namespace concept), and the aspect
    must be the one configured for the first path segment. The context must
    be accepted, and a domain context needs a matching pattern.
    """
    node_id, context = document["@id"], document["@context"]
    if not isinstance(node_id, str) or not isinstance(context, str):
        raise WriteRejected("@id and @context must be strings")
    parsed = _parse(context)
    access.require(parsed.domain_name)
    id_path = unquote(urlparse(node_id).path)
    if id_path != path:
        raise WriteRejected(f"@id {node_id!r} does not belong to the path {path!r}")
    segment = path.strip("/").split("/", 1)[0]
    expected = get_settings().IFDD_ASPECTS.get(segment)
    if aspect != expected:
        raise WriteRejected(f"aspect {aspect!r} does not match the path segment {segment!r}")
    return DocumentKey(
        id=node_id,
        id_path=id_path,
        context=context,
        aspect=aspect,
        domain=parsed.domain_name,
    )


def _parse(context: str):
    try:
        return parse_context(context)
    except ContextError as err:
        raise WriteRejected(str(err)) from err


def _split(document: Mapping[str, Any]) -> tuple[dict, SourceMeta]:
    try:
        return split_cache_meta(document)
    except CacheMetaError as err:
        raise WriteRejected(str(err)) from err


def _period(meta: SourceMeta, now: datetime) -> Period:
    try:
        return requested_period(meta.valid_not_before, meta.valid_not_after, now)
    except PeriodError as err:
        raise WriteRejected(str(err)) from err


def _content(document: dict, meta: SourceMeta) -> Content:
    """Normalise a document (compact with its own context, expand) for storing.

    The context must define the six c_* terms in a namespace ending with
    ``/`` or ``#`` (:func:`~ifdd.be.core.contexts.cache_namespace`).
    """
    try:
        cache_namespace(document["@context"])
    except ContextError as err:
        raise WriteRejected(str(err)) from err
    processor = get_processor()
    compacted = processor.compact(
        document, document["@context"], options={"graph": False, "compactArrays": True}
    )
    expanded_list = processor.expand(compacted, options=None)
    if not expanded_list:
        raise WriteRejected("the document has no content besides @id and @context")
    expanded = expanded_list[0]
    leaked = cache_iris_in(expanded)
    if leaked:
        raise WriteRejected(
            "c_* terms must be sent as plain terms of the context, not as IRIs: "
            + ", ".join(leaked)
        )
    return Content(
        canonical=repository.canonical(expanded),
        created=meta.created,
        modified=meta.modified,
        document=compacted,
        expanded=expanded,
    )


def _versioning() -> bool:
    return get_settings().IFDD_VERSIONING
