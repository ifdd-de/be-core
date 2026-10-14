"""IFDD_VERSIONING=false: no history in system time, valid time periods stay.

What a write replaces is deleted instead of ended; the table holds only what
the backend knows now. The valid-time behaviour is the same as with
versioning.
"""

import pytest

PAST = "2020-01-01T00:00:00+00:00"
FUTURE = "2099-01-01T00:00:00+00:00"


@pytest.fixture
def api(make_api):
    with make_api(IFDD_VERSIONING=False) as api:
        yield api


def test_a_change_replaces_the_row_instead_of_ending_it(api):
    api.put("t1", objName="A", c_validNotBefore=PAST)
    api.put("t1", objName="B")
    rows = api.rows("t1")
    assert all(row["current"] for row in rows)
    assert [row["json"]["objName"] for row in rows] == ["A", "B"]  # past part, new part


def test_valid_time_periods_are_kept(api):
    api.put("t1", objName="A", c_validNotBefore=PAST)
    api.put("t1", objName="B", c_validNotBefore=FUTURE)
    assert [row["json"]["objName"] for row in api.rows("t1")] == ["A", "B"]
    assert api.get("t1", at="2099-06-01T00:00:00Z").json()["product:objName"] == "B"


def test_writing_the_same_document_again_changes_nothing(api):
    api.put("t1", objName="A")
    assert api.put("t1", objName="A").json() == {"message": "No changes detected"}
    assert len(api.rows("t1")) == 1


def test_an_unchanged_write_confirms_without_versioning_too(api):
    api.put("t1", objName="A")
    [before] = api.rows("t1")
    api.put("t1", objName="A")
    [after] = api.rows("t1")
    assert after["cache_updated"] > before["cache_updated"]


def test_delete_removes_the_rows(api):
    api.put("t1", objName="A")
    api.delete("t1", c_validNotBefore=PAST)
    assert api.rows("t1") == []
