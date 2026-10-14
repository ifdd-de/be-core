"""Two writers of one document at the same time.

Each write reads the current versions, plans and writes. Without the
per-document lock both writers could read the same versions; the second would
then hit the exclusion constraint. The test holds the first writer right
after it read, long enough for the second to read the same versions if it
could.
"""

import asyncio

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from ifdd.be.core import repository, writes
from ifdd.be.core.config import configure
from ifdd.be.core.contexts import Access

from .conftest import DB_URL, SEGMENTS, settings_for, sql

HOLD_SECONDS = 0.5


@pytest.fixture
async def sessions(schema_server):
    configure(settings_for(schema_server))
    engine = create_async_engine(DB_URL)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
def first_reader_waits(monkeypatch):
    """Let the first writer pause after reading until a second one has read too."""
    original = repository.current_versions
    readers = []
    second_read = asyncio.Event()

    async def reading_then_waiting(*args, **kwargs):
        versions = await original(*args, **kwargs)
        readers.append(len(versions))
        if len(readers) == 2:
            second_read.set()
        else:
            try:
                await asyncio.wait_for(second_read.wait(), HOLD_SECONDS)
            except TimeoutError:
                pass  # the second writer is waiting for the lock
        return versions

    monkeypatch.setattr(repository, "current_versions", reading_then_waiting)
    return readers


def document(schema_server, name):
    return {
        "@context": f"{schema_server}/v1/product.jsonld",
        "@id": f"https://rest.test/{SEGMENTS['product']}/race",
        "objName": name,
    }


async def write(sessions, doc):
    async with sessions() as session, session.begin():
        return await writes.put(session, doc, "product", "/products/race", Access(patterns=()))


async def test_concurrent_writes_of_one_document_are_serialised(
    schema_server, sessions, first_reader_waits
):
    await write(sessions, document(schema_server, "start"))
    first_reader_waits.clear()

    outcomes = await asyncio.gather(
        write(sessions, document(schema_server, "first")),
        write(sessions, document(schema_server, "second")),
    )

    assert outcomes == [writes.Outcome.UPDATED, writes.Outcome.UPDATED]
    # the second writer read the result of the first one, not the same state
    assert first_reader_waits[0] != first_reader_waits[1]
    open_ended = sql(
        "SELECT json->>'objName' AS name FROM nodes "
        "WHERE upper_inf(sys_period) AND upper_inf(valid_period)"
    )
    assert len(open_ended) == 1
