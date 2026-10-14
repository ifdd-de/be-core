"""Schema maintenance commands.

The table definition is taken from :mod:`ifdd.be.core.models`; the standalone copy
that the original tools/create.py carried has been removed, so the DDL and the
ORM mapping can no longer drift apart.

There are no migrations: ``create_tables`` creates what is missing and never
changes an existing table. A ``nodes`` table from before the bitemporal model
(26.10.2 and earlier), or one without the ``domain`` column of the context
access rules, is refused with a message; drop it and load the data again.
"""

import asyncio
from datetime import timedelta

from sqlalchemy import delete, func, inspect, select, update
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.sql import text

from ..config import get_settings
from ..db.base import metadata
from ..models import REQUIRED_EXTENSIONS, Node


class OutdatedTableError(RuntimeError):
    """The database holds a nodes table this version cannot use."""


def _engine():
    """A short-lived engine for one maintenance command."""
    url = get_settings().IFDD_SERVICE_DB_URL
    if not url:
        raise RuntimeError("IFDD_SERVICE_DB_URL is not configured.")
    return create_async_engine(url)


def _refuse_outdated_table(sync_conn) -> None:
    """Raise :class:`OutdatedTableError` for a nodes table of an older layout."""
    inspector = inspect(sync_conn)
    if not inspector.has_table(Node.__tablename__):
        return
    columns = {column["name"] for column in inspector.get_columns(Node.__tablename__)}
    if "sys_period" not in columns:
        raise OutdatedTableError(
            "The nodes table has the layout of ifdd-be-core 26.10.2 or earlier "
            "(no sys_period). There are no migrations: drop the table "
            "(DROP TABLE nodes) and load the data again."
        )
    if "domain" not in columns:
        raise OutdatedTableError(
            "The nodes table has the layout of ifdd-be-core before context access "
            "rules (no domain column). There are no migrations: drop the table "
            "(DROP TABLE nodes) and load the data again."
        )


async def create_tables() -> None:
    """Create the extensions, the nodes table and its indexes where missing.

    Raises:
        OutdatedTableError: An existing nodes table has an older layout.
    """
    engine = _engine()
    try:
        async with engine.begin() as conn:
            for extension in REQUIRED_EXTENSIONS:
                await conn.execute(text(f"CREATE EXTENSION IF NOT EXISTS {extension}"))
            await conn.run_sync(_refuse_outdated_table)
            await conn.run_sync(metadata.create_all)
    finally:
        await engine.dispose()


async def purge_expired(max_age_hours: int = 50) -> None:
    """End the current versions that were not written for ``max_age_hours``.

    With versioning they end in system time and stay as history; without,
    they are deleted.
    """
    engine = _engine()
    try:
        async with engine.begin() as conn:
            now = await conn.scalar(select(func.clock_timestamp()))
            stale = (Node.is_current, Node.cache_updated < now - timedelta(hours=max_age_hours))
            if get_settings().IFDD_VERSIONING:
                statement = (
                    update(Node)
                    .where(*stale)
                    .values(sys_period=func.tstzrange(func.lower(Node.sys_period), now))
                )
            else:
                statement = delete(Node).where(*stale)
            await conn.execute(statement)
    finally:
        await engine.dispose()


def main_create() -> None:
    """Entry point of ``ifdd-be-create-tables`` (run by ``prestart.sh``)."""
    try:
        asyncio.run(create_tables())
    except OutdatedTableError as err:
        raise SystemExit(f"ifdd-be-create-tables: {err}") from None


def main_purge() -> None:
    """Entry point of ``ifdd-be-purge``: end versions not written for 50 hours."""
    asyncio.run(purge_expired())
