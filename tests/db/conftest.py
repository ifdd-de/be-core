"""Tests against a real PostgreSQL (16 or later; CI and the README use 18).

Set ``IFDD_TEST_DB_URL`` to a database the tests may wipe, e.g.::

    IFDD_TEST_DB_URL=postgresql+psycopg://ifdd:ifdd@localhost:5432/ifdd_test

Without it every test in this directory is skipped. The tests drop and create
the ``nodes`` table once per run and empty it before each test.

The JSON-LD contexts come from a local HTTP server that serves
``tests/db/contexts`` (a product and a location schema with the c_* terms);
documents use the made-up hosts ``rest.test`` and ``type.test``.
"""

from __future__ import annotations

import asyncio
import os
import threading
from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional

import psycopg
import pytest
from psycopg.rows import dict_row
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DB_URL = os.environ.get("IFDD_TEST_DB_URL", "")
BE_URL = "https://rest.test"
TYPE_URL = "https://type.test/v1"
CONTEXTS = Path(__file__).parent / "contexts"
SEGMENTS = {"product": "products", "location": "locations"}


@pytest.fixture(scope="session")
def schema_server():
    """Serves the test contexts as the schema service would: <url>/v1/product.jsonld."""

    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), partial(Quiet, directory=str(CONTEXTS)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def settings_for(schema_server: str, **overrides):
    from ifdd.be.core.config import CoreSettings

    values = dict(
        IFDD_SERVICE_DB_URL=DB_URL,
        IFDD_SCHEMA_URL=f"{schema_server}/v1",
        IFDD_TYPE_URL=TYPE_URL,
        IFDD_BE_AUTH_ENABLED=False,
        IFDD_BE_SSL_ENABLED=False,
        IFDD_DB_POOL_SIZE=5,
    )
    values.update(overrides)
    return CoreSettings(**values)


@pytest.fixture(scope="session")
def nodes_table(schema_server):
    """A fresh nodes table, created by the same command an instance runs."""
    if not DB_URL:
        pytest.skip("IFDD_TEST_DB_URL is not set")
    from ifdd.be.core.config import configure
    from ifdd.be.core.tools.schema import create_tables

    async def recreate():
        engine = create_async_engine(DB_URL)
        async with engine.begin() as conn:
            await conn.execute(text("DROP TABLE IF EXISTS nodes"))
        await engine.dispose()
        configure(settings_for(schema_server))
        await create_tables()

    asyncio.run(recreate())


def libpq_url() -> str:
    return DB_URL.replace("postgresql+psycopg://", "postgresql://", 1)


def sql(query: str, *params: Any) -> list[dict]:
    """Run plain SQL in its own connection; for setting up and checking the table."""
    with psycopg.connect(libpq_url(), autocommit=True, row_factory=dict_row) as conn:
        cursor = conn.execute(query, params or None)
        return cursor.fetchall() if cursor.description else []


@pytest.fixture(autouse=True)
def empty_table(request):
    """Every test here needs the database and starts with an empty table."""
    if not DB_URL:
        pytest.skip("IFDD_TEST_DB_URL is not set")
    request.getfixturevalue("nodes_table")
    sql("TRUNCATE nodes RESTART IDENTITY")


class Api:
    """The REST API as the tests use it; documents are built from short arguments."""

    def __init__(self, client, schema_server: str):
        self.client = client
        self.schema_server = schema_server

    # -- documents ---------------------------------------------------------------
    def context(self, aspect: str = "product") -> str:
        return f"{self.schema_server}/v1/{aspect}.jsonld"

    def path(self, uid: str, aspect: str = "product") -> str:
        return f"/{SEGMENTS[aspect]}/{uid}"

    def node_id(self, uid: str, aspect: str = "product") -> str:
        return f"{BE_URL}{self.path(uid, aspect)}"

    def document(self, uid: str, aspect: str = "product", **fields) -> dict:
        return {"@context": self.context(aspect), "@id": self.node_id(uid, aspect), **fields}

    # -- requests ----------------------------------------------------------------
    def put(self, uid: str, aspect: str = "product", **fields):
        body = {"json": self.document(uid, aspect, **fields), "aspect": aspect}
        return self.client.put(self.path(uid, aspect), json=body)

    def patch(self, uid: str, aspect: str = "product", **fields):
        body = {"json": self.document(uid, aspect, **fields), "aspect": aspect}
        return self.client.patch(self.path(uid, aspect), json=body)

    def delete(self, uid: str, aspect: str = "product", **meta):
        return self.client.request("DELETE", self.path(uid, aspect), json=meta or None)

    def get(self, uid: str, aspect: str = "product", at: Optional[str] = None, **headers):
        params = {"at": at} if at else None
        return self.client.get(self.path(uid, aspect), params=params, headers=headers)

    def list(self, aspect: str = "product", **params):
        return self.client.get(f"/{SEGMENTS[aspect]}", params=params)

    # -- table state -------------------------------------------------------------
    def rows(self, uid: str, aspect: str = "product") -> list[dict]:
        """All stored versions of a document, current and retired."""
        return sql(
            "SELECT json, valid_period, sys_period, upper_inf(sys_period) AS current, "
            "src_created, src_modified, cache_created, cache_updated "
            "FROM nodes WHERE id = %s ORDER BY lower(sys_period), lower(valid_period)",
            self.node_id(uid, aspect),
        )

    def current(self, uid: str, aspect: str = "product") -> list[dict]:
        return [row for row in self.rows(uid, aspect) if row["current"]]


@pytest.fixture
def make_api(schema_server, nodes_table):
    """Build an Api with settings overrides: ``with make_api(IFDD_VERSIONING=False) as api``."""
    from fastapi.testclient import TestClient

    from ifdd.be.core import create_app

    @contextmanager
    def make(**overrides):
        app = create_app(settings_for(schema_server, **overrides))
        with TestClient(app) as client:
            yield Api(client, schema_server)

    return make


@pytest.fixture
def api(make_api):
    with make_api() as api:
        yield api
