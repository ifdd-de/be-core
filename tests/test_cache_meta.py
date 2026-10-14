"""Taking the c_* cache metadata out of a document and adding it back.

ifdd.be.core.cache_meta, without a database or a JSON-LD processor.
"""

from datetime import datetime, timezone

import pytest

from ifdd.be.core.cache_meta import (
    CACHE_TERMS,
    XSD_DATETIME,
    CacheMetaError,
    add_to_compacted,
    add_to_expanded,
    cache_iris_in,
    split_cache_meta,
    stored_values,
)

UTC = timezone.utc
DOC = {"@context": "https://schema/v1/product.jsonld", "@id": "https://rest/products/1"}


def test_the_six_terms_are_known():
    assert set(CACHE_TERMS) == {
        "c_created",
        "c_modified",
        "c_validNotBefore",
        "c_validNotAfter",
        "c_cacheCreated",
        "c_cacheUpdated",
    }


def test_source_terms_are_taken_out_and_kept():
    content, meta = split_cache_meta(
        {
            **DOC,
            "objName": "T1",
            "c_created": "2020-01-01T00:00:00+00:00",
            "c_modified": "2021-06-01T12:00:00Z",
            "c_validNotBefore": "2022-01-01T00:00:00+01:00",
            "c_validNotAfter": "2030-01-01T00:00:00Z",
        }
    )
    assert content == {**DOC, "objName": "T1"}
    assert meta.created == datetime(2020, 1, 1, tzinfo=UTC)
    assert meta.modified == datetime(2021, 6, 1, 12, tzinfo=UTC)
    assert meta.valid_not_before == datetime(2021, 12, 31, 23, tzinfo=UTC)
    assert meta.valid_not_after == datetime(2030, 1, 1, tzinfo=UTC)


def test_backend_terms_sent_by_a_client_are_discarded():
    content, meta = split_cache_meta(
        {**DOC, "c_cacheCreated": "1999-01-01T00:00:00Z", "c_cacheUpdated": "1999-01-01T00:00:00Z"}
    )
    assert content == DOC
    assert meta.created is None and meta.valid_not_before is None


def test_an_unknown_cache_term_is_rejected():
    with pytest.raises(CacheMetaError, match="c_expire"):
        split_cache_meta({**DOC, "c_expire": "2030-01-01T00:00:00Z"})


def test_a_date_time_without_time_zone_is_read_as_utc():
    _, meta = split_cache_meta({**DOC, "c_created": "2020-01-01T00:00:00"})
    assert meta.created == datetime(2020, 1, 1, tzinfo=UTC)


def test_a_json_ld_value_object_is_accepted():
    _, meta = split_cache_meta(
        {**DOC, "c_created": {"@value": "2020-01-01T00:00:00Z", "@type": "xsd:dateTime"}}
    )
    assert meta.created == datetime(2020, 1, 1, tzinfo=UTC)


@pytest.mark.parametrize("value", ["yesterday", 2020, None])
def test_a_value_that_is_no_date_time_is_rejected(value):
    with pytest.raises(CacheMetaError, match="c_created"):
        split_cache_meta({**DOC, "c_created": value})


def test_the_document_passed_in_is_not_changed():
    sent = {**DOC, "c_created": "2020-01-01T00:00:00Z"}
    split_cache_meta(sent)
    assert "c_created" in sent


def test_cache_terms_written_as_iris_are_found_in_the_expanded_form():
    expanded = {
        "@id": "https://rest/products/1",
        "https://type/v1/product/objName": [{"@value": "T1"}],
        "https://type/v1/product/c_created": [{"@value": "2020"}],
        "http://example.org/ns#c_modified": [{"@value": "2020"}],
    }
    assert sorted(cache_iris_in(expanded)) == [
        "http://example.org/ns#c_modified",
        "https://type/v1/product/c_created",
    ]


def test_stored_values_leave_out_what_is_not_set():
    """An open-ended valid time has no c_validNotAfter; unsent source dates stay absent."""
    t = datetime(2026, 1, 1, tzinfo=UTC)
    values = stored_values(
        created=None,
        modified=None,
        valid_not_before=t,
        valid_not_after=None,
        cache_created=t,
        cache_updated=t,
    )
    assert set(values) == {"c_validNotBefore", "c_cacheCreated", "c_cacheUpdated"}


def test_values_are_added_as_plain_terms_to_a_compacted_document():
    t = datetime(2026, 1, 1, tzinfo=UTC)
    document = add_to_compacted(dict(DOC), {"c_cacheUpdated": t})
    assert document["c_cacheUpdated"] == "2026-01-01T00:00:00+00:00"


def test_values_are_answered_in_utc_whatever_the_database_time_zone():
    """psycopg returns timestamptz in the time zone of the database session;
    the answer must not depend on it (found with a cluster in Europe/Berlin)."""
    from zoneinfo import ZoneInfo

    berlin = datetime(2020, 1, 1, 1, 0, tzinfo=ZoneInfo("Europe/Berlin"))
    assert add_to_compacted({}, {"c_created": berlin}) == {"c_created": "2020-01-01T00:00:00+00:00"}
    expanded = add_to_expanded({}, {"c_created": berlin}, "https://type/v1/product/")
    assert expanded["https://type/v1/product/c_created"][0]["@value"] == "2020-01-01T00:00:00+00:00"


def test_values_are_added_with_the_namespace_iri_to_an_expanded_document():
    t = datetime(2026, 1, 1, tzinfo=UTC)
    expanded = add_to_expanded({}, {"c_cacheUpdated": t}, "https://type/v1/product/")
    assert expanded == {
        "https://type/v1/product/c_cacheUpdated": [
            {"@type": XSD_DATETIME, "@value": "2026-01-01T00:00:00+00:00"}
        ]
    }
