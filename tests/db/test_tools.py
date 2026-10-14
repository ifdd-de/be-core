"""The maintenance commands ifdd-be-create-tables and ifdd-be-purge."""

import pytest

from ifdd.be.core.config import configure
from ifdd.be.core.tools.schema import OutdatedTableError, create_tables, purge_expired

from .conftest import DB_URL, settings_for, sql


async def test_a_table_of_the_old_layout_is_refused(schema_server):
    """No migrations: a nodes table from 26.10.2 must be dropped by hand."""
    sql("DROP SCHEMA IF EXISTS old_layout CASCADE")
    sql("CREATE SCHEMA old_layout")
    sql("CREATE TABLE old_layout.nodes (id varchar, context varchar, valid tstzrange)")
    url = DB_URL + ("&" if "?" in DB_URL else "?") + "options=-csearch_path%3Dold_layout"
    configure(settings_for(schema_server, IFDD_SERVICE_DB_URL=url))
    try:
        with pytest.raises(OutdatedTableError, match="DROP TABLE nodes"):
            await create_tables()
    finally:
        sql("DROP SCHEMA old_layout CASCADE")


async def test_a_table_without_the_domain_column_is_refused(schema_server):
    """Context access rules need the domain column; there are no migrations."""
    sql("DROP SCHEMA IF EXISTS no_domain CASCADE")
    sql("CREATE SCHEMA no_domain")
    sql("CREATE TABLE no_domain.nodes (id varchar, context varchar, sys_period tstzrange)")
    url = DB_URL + ("&" if "?" in DB_URL else "?") + "options=-csearch_path%3Dno_domain"
    configure(settings_for(schema_server, IFDD_SERVICE_DB_URL=url))
    try:
        with pytest.raises(OutdatedTableError, match="no domain column"):
            await create_tables()
    finally:
        sql("DROP SCHEMA no_domain CASCADE")


async def test_create_tables_leaves_an_existing_table_alone(api, schema_server):
    api.put("t1", objName="A")
    configure(settings_for(schema_server))
    await create_tables()
    assert len(api.rows("t1")) == 1


def age(uid_path: str, hours: int) -> None:
    sql(
        "UPDATE nodes SET cache_updated = cache_updated - make_interval(hours => %s) "
        "WHERE id_path = %s",
        hours,
        uid_path,
    )


async def test_purge_ends_stale_versions_and_keeps_them_as_history(api, schema_server):
    api.put("stale", objName="A")
    api.put("fresh", objName="B")
    age("/products/stale", 100)
    configure(settings_for(schema_server))
    await purge_expired(max_age_hours=50)

    assert api.get("stale").status_code == 404
    assert api.get("fresh").status_code == 200
    assert [row["current"] for row in api.rows("stale")] == [False]


async def test_purge_spares_a_document_its_source_keeps_confirming(api, schema_server):
    api.put("t1", objName="A")
    age("/products/t1", 100)
    api.put("t1", objName="A")  # the source sends it again, unchanged
    configure(settings_for(schema_server))
    await purge_expired(max_age_hours=50)
    assert api.get("t1").status_code == 200


async def test_purge_without_versioning_deletes(make_api, schema_server):
    with make_api(IFDD_VERSIONING=False) as api:
        api.put("stale", objName="A")
        age("/products/stale", 100)
        configure(settings_for(schema_server, IFDD_VERSIONING=False))
        await purge_expired(max_age_hours=50)
        assert api.rows("stale") == []
