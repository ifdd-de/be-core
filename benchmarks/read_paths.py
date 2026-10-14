"""Where the time of a read goes: database or JSON-LD processing.

Optional, not part of the test suite. It fills the table given by
IFDD_TEST_DB_URL (the table is dropped and created!) with DOCUMENTS product
documents through the write path and then times, per request:

* the database part of GET /{segment}/{id} and of a list page,
* the JSON-LD part of GET /{segment}/{id} (merge + PyLD compaction),
* the presentation of a list page (no PyLD).

The contexts come from tests/db/contexts, served on a local port.

    IFDD_TEST_DB_URL=postgresql+psycopg://... python benchmarks/read_paths.py [DOCUMENTS]

The numbers compare the parts with each other on one machine; they are no
absolute figures for a deployment (no network, no proxy, no TLS).
"""

from __future__ import annotations

import asyncio
import os
import statistics
import sys
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from ifdd.be.core import presentation, repository, writes
from ifdd.be.core.config import CoreSettings, configure
from ifdd.be.core.contexts import Access
from ifdd.be.core.helper import utc_now
from ifdd.be.core.tools.schema import create_tables

# The development root: every domain context; the benchmark has none.
ACCESS = Access(patterns=("ifdd.de",))

CONTEXTS = Path(__file__).resolve().parent.parent / "tests" / "db" / "contexts"
REPEAT = 200


def serve_contexts() -> str:
    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), partial(Quiet, directory=str(CONTEXTS)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{httpd.server_address[1]}/v1"


def product(schema_url: str, number: int) -> dict:
    """A product document of typical size (about a dozen fields)."""
    return {
        "@context": f"{schema_url}/product.jsonld",
        "@id": f"https://rest.test/products/p{number}",
        "objName": f"Transformer {number}",
        "objType": f"type{number % 40}",
        "objScope": f"scope{number % 5}",
        "description": f"Power transformer {number}, 110/20 kV, outdoor, oil-immersed",
        "containedIn": f"https://rest.test/locations/l{number % 300}",
        "c_created": "2020-01-01T00:00:00Z",
        "c_modified": "2024-06-01T00:00:00Z",
        "c_validNotBefore": "2020-01-01T00:00:00Z",
    }


def report(label: str, samples: list[float]) -> None:
    ms = sorted(s * 1000 for s in samples)
    p95 = ms[int(len(ms) * 0.95) - 1]
    print(f"{label:<48} median {statistics.median(ms):7.3f} ms   p95 {p95:7.3f} ms")


async def main(documents: int) -> None:
    db_url = os.environ["IFDD_TEST_DB_URL"]
    schema_url = serve_contexts()
    configure(
        CoreSettings(
            IFDD_SERVICE_DB_URL=db_url,
            IFDD_SCHEMA_URL=schema_url,
            IFDD_TYPE_URL="https://type.test/v1",
        )
    )
    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS nodes"))
    await create_tables()
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    started = time.perf_counter()
    for number in range(documents):
        async with sessions() as session, session.begin():
            doc = product(schema_url, number)
            await writes.put(session, doc, "product", f"/products/p{number}", ACCESS)
    print(f"{documents} documents written in {time.perf_counter() - started:.1f} s")
    async with engine.begin() as conn:
        await conn.execute(text("ANALYZE nodes"))

    db_single, ld_single, db_page, page_presentation = [], [], [], []
    async with sessions() as session:
        for round_ in range(REPEAT):
            path = f"/products/p{(round_ * 7919) % documents}"
            t0 = time.perf_counter()
            rows = await repository.documents_at_path(session, utc_now(), path)
            t1 = time.perf_counter()
            presentation.single_document(rows)
            t2 = time.perf_counter()
            db_single.append(t1 - t0)
            ld_single.append(t2 - t1)

            t0 = time.perf_counter()
            _, page = await repository.list_nodes(
                session,
                utc_now(),
                ACCESS,
                context=f"{schema_url}/product.jsonld",
                start=0,
                end=100,
            )
            t1 = time.perf_counter()
            [presentation.list_entry(row) for row in page]
            t2 = time.perf_counter()
            db_page.append(t1 - t0)
            page_presentation.append(t2 - t1)

    print(f"\nreads, {REPEAT} rounds, {documents} documents in the table:")
    report("GET single: database", db_single)
    report("GET single: JSON-LD merge + compaction (PyLD)", ld_single)
    report("list page of 100: database (page + count)", db_page)
    report("list page of 100: presentation (no PyLD)", page_presentation)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 2000))
