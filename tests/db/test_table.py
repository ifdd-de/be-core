"""The nodes table itself: constraints and indexes, checked with plain SQL.

The exclusion constraint is the safety net behind the write lock: no two
versions of one document (same @id and @context) may overlap in system time
and valid time at once.
"""

import psycopg
import pytest

from .conftest import sql

INSERT = (
    "INSERT INTO nodes (id, id_path, context, aspect, sys_period, valid_period, "
    "cache_created, cache_updated, json, expanded) "
    "VALUES ('urn:x', '/products/x', %s, 'product', %s::tstzrange, %s::tstzrange, "
    "now(), now(), '{}', '{}')"
)
CTX = "https://schema/v1/product.jsonld"


def insert(sys_period: str, valid_period: str, context: str = CTX) -> None:
    sql(INSERT, context, sys_period, valid_period)


def test_overlap_in_both_times_is_refused():
    insert("[2026-01-01,)", "[2020-01-01,)")
    with pytest.raises(psycopg.errors.ExclusionViolation):
        insert("[2026-06-01,)", "[2025-01-01,2030-01-01)")


def test_overlap_in_one_time_only_is_allowed():
    insert("[2026-01-01,)", "[2020-01-01,2027-01-01)")
    insert("[2026-01-01,)", "[2027-01-01,)")  # same system time, next valid period
    insert("[2025-01-01,2026-01-01)", "[2020-01-01,)")  # history: earlier system time
    assert len(sql("SELECT 1 FROM nodes")) == 3


def test_other_contexts_of_the_same_document_do_not_collide():
    insert("[2026-01-01,)", "[2020-01-01,)")
    insert("[2026-01-01,)", "[2020-01-01,)", context="https://schema/v1/location.jsonld")


@pytest.mark.parametrize(
    "sys_period, valid_period",
    [
        ("[2026-01-01,2026-01-01)", "[2020-01-01,)"),  # empty system time
        ("[2026-01-01,)", "[2020-01-01,2020-01-01)"),  # empty valid time
        ("[2026-01-01,)", "(,2030-01-01)"),  # valid time without a start
    ],
)
def test_empty_or_unbounded_periods_are_refused(sys_period, valid_period):
    with pytest.raises(psycopg.errors.CheckViolation):
        insert(sys_period, valid_period)


def test_required_extensions_are_installed():
    names = {row["extname"] for row in sql("SELECT extname FROM pg_extension")}
    assert {"btree_gist", "pg_trgm"} <= names


def test_every_read_index_covers_current_rows_only():
    indexes = sql(
        "SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'nodes' "
        "AND indexname LIKE 'ix_%%'"
    )
    assert len(indexes) == 12
    for index in indexes:
        assert index["indexdef"].endswith("WHERE upper_inf(sys_period)"), index["indexname"]
