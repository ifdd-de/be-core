"""The planner picks the partial read indexes for realistic data.

A fixture fills the table with SQL: 20,000 current versions (half of them in a
second context, a tenth in a domain context, a few valid only from 2099 on)
and 20,000 retired ones. Every read also carries the access filter on the
domain column, as the routers send it. Each
test runs a repository function, captures the SQL it sends and checks the
plan PostgreSQL chooses with its default settings.

Planner decisions depend on the PostgreSQL version and the statistics; these
tests document what PostgreSQL 18 chooses for this data and guard against
queries that no longer match an index (expression or partial condition).
"""

from datetime import datetime, timezone

import psycopg
import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from ifdd.be.core import repository
from ifdd.be.core.config import configure
from ifdd.be.core.contexts import Access

from .conftest import DB_URL, libpq_url, settings_for, sql

NOW = datetime.now(timezone.utc)
IN_2099 = datetime(2099, 6, 1, tzinfo=timezone.utc)
PRODUCT = "https://schema.test/v1/product.jsonld"
LOCATION = "https://schema.test/v1/location.jsonld"
DOMAIN = "breaker.grid.example.ifdd.de"
ACCESS = Access(patterns=("grid.example.ifdd.de",))
VOLUME = 20_000

FILL = """
INSERT INTO nodes (id, id_path, context, aspect, domain, sys_period, valid_period,
                   cache_created, cache_updated, json, expanded)
SELECT 'https://rest.test/products/n' || g,
       '/products/n' || g,
       CASE WHEN g %% 10 = 5 THEN 'https://schema.test/v1/' || %(domain)s || '.jsonld'
            WHEN g %% 2 = 0 THEN %(product)s ELSE %(location)s END,
       'product',
       CASE WHEN g %% 10 = 5 THEN %(domain)s ELSE NULL END,
       CASE WHEN %(retired)s THEN tstzrange(now() - interval '2 days', now() - interval '1 day')
            ELSE tstzrange(now() - interval '1 day', NULL) END,
       CASE WHEN g %% 1000 = 0 THEN tstzrange('2099-01-01', NULL)
            ELSE tstzrange('2020-01-01', '2030-01-01') END,
       now() - g * interval '1 second',
       now() - g * interval '1 second',
       jsonb_build_object('@id', 'https://rest.test/products/n' || g,
                          'objName', 'Node ' || g,
                          'objType', 'type' || (g %% 200),
                          'objScope', 'scope' || (g %% 7)),
       '{}'::jsonb
FROM generate_series(1, %(volume)s) AS g
"""


@pytest.fixture
def volume():
    with psycopg.connect(libpq_url(), autocommit=True) as conn:
        for retired in (True, False):
            parameters = {
                "product": PRODUCT,
                "location": LOCATION,
                "domain": DOMAIN,
                "retired": retired,
            }
            conn.execute(FILL, {**parameters, "volume": VOLUME})
    sql("ANALYZE nodes")


async def plan_of(query_function, schema_server) -> str:
    """The EXPLAIN output of the SELECT statements the function runs."""
    configure(settings_for(schema_server))
    engine = create_async_engine(DB_URL)
    statements = []

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def capture(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append((statement, parameters))

    try:
        async with engine.connect() as conn:
            await query_function(AsyncSession(bind=conn))
            plans = []
            for statement, parameters in statements:
                result = await conn.exec_driver_sql("EXPLAIN " + statement, parameters)
                plans.append("\n".join(row[0] for row in result))
            return "\n".join(plans)
    finally:
        await engine.dispose()


@pytest.mark.parametrize(
    "description, query, index",
    [
        (
            "one aspect at an instant only few versions are valid at",
            lambda s: repository.list_nodes(s, IN_2099, ACCESS, context=PRODUCT),
            "ix_nodes_current_context_valid",
        ),
        (
            "single document by path",
            lambda s: repository.documents_at_path(s, NOW, "/products/n1234"),
            "ix_nodes_current_id_path",
        ),
        (
            "document by @id (graph traversal)",
            lambda s: repository.generic_documents_with_id(
                s, NOW, "https://rest.test/products/n1234"
            ),
            "ix_nodes_current_id",
        ),
        (
            "filter by objType",
            lambda s: repository.list_nodes(s, NOW, ACCESS, type_id="type7"),
            "ix_nodes_current_json",
        ),
        (
            "full-text search",
            lambda s: repository.list_nodes(s, NOW, ACCESS, search="Node 12345"),
            "ix_nodes_current_json_trgm",
        ),
        (
            "first page sorted by a document field",
            lambda s: repository.list_nodes(s, NOW, ACCESS, sort="objName", end=50),
            "ix_nodes_current_objname",
        ),
        (
            "first page of all documents by c_cacheUpdated",
            lambda s: repository.list_nodes(s, NOW, ACCESS, sort="c_cacheUpdated", end=50),
            "ix_nodes_current_cache_updated",
        ),
    ],
)
async def test_the_planner_uses_the_index(volume, schema_server, description, query, index):
    plan = await plan_of(query, schema_server)
    assert index in plan, f"{description}:\n{plan}"
    assert "Seq Scan" not in plan, f"{description}:\n{plan}"
