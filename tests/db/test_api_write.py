"""PUT, PATCH and DELETE through the REST API, checked against the stored rows.

Valid time in the scenarios: PAST (2020) and FUTURE (2099) are sent as
c_validNotBefore/c_validNotAfter; "now" is the database clock of the write.
``api.rows(uid)`` shows every stored version, ``api.current(uid)`` the ones
the backend knows now (open-ended system time).
"""

from datetime import datetime, timezone

PAST = "2020-01-01T00:00:00+00:00"
MIDDLE = "2030-01-01T00:00:00+00:00"
FUTURE = "2099-01-01T00:00:00+00:00"


def utc(iso: str) -> datetime:
    return datetime.fromisoformat(iso).astimezone(timezone.utc)


def valid(row) -> tuple:
    """The valid period of a row as (lower, upper) ISO strings, None = open."""
    period = row["valid_period"]
    return (
        period.lower.astimezone(timezone.utc).isoformat() if period.lower else None,
        period.upper.astimezone(timezone.utc).isoformat() if period.upper else None,
    )


def api_text(value: datetime) -> str:
    """A stored time as the API writes it."""
    return value.astimezone(timezone.utc).isoformat()


def name_of(row) -> str:
    return row["json"]["objName"]


# --- PUT: creating ----------------------------------------------------------------


def test_put_creates_a_document_valid_from_now_on(api):
    before = datetime.now(timezone.utc)
    answer = api.put("t1", objName="Trafo 1")
    after = datetime.now(timezone.utc)

    assert answer.status_code == 201, answer.text
    [row] = api.rows("t1")
    assert row["current"]
    assert before <= row["valid_period"].lower <= after
    assert row["valid_period"].upper is None
    assert row["cache_created"] == row["cache_updated"] == row["sys_period"].lower


def test_cache_metadata_is_stored_in_columns_not_in_the_document(api):
    api.put(
        "t1",
        objName="Trafo 1",
        c_created=PAST,
        c_modified=PAST,
        c_validNotBefore=PAST,
        c_cacheCreated=FUTURE,  # backend values from a client are discarded
        c_cacheUpdated=FUTURE,
    )
    [row] = api.rows("t1")
    assert not [key for key in row["json"] if key.startswith("c_")]
    expanded = api.client.get(api.path("t1"), headers={"json-ld-expanded": "true"}).json()
    assert row["src_created"] == row["src_modified"] == utc(PAST)
    assert valid(row) == (PAST, None)
    assert row["cache_created"] != utc(FUTURE)
    # the stored expanded form has no c_* either; GET adds them from the columns
    stored = api.rows("t1")[0]
    assert "c_" not in str(stored["json"])
    assert any(iri.endswith("/c_created") for iri in expanded)


# --- PUT: idempotency -----------------------------------------------------------------


def test_writing_the_same_document_twice_stores_one_version(api):
    """Up to 26.10.2 the second PUT stored a spurious version (handover 9.9)."""
    assert api.put("t1", objName="Trafo 1").status_code == 201
    answer = api.put("t1", objName="Trafo 1")
    assert answer.status_code == 200
    assert answer.json() == {"message": "No changes detected"}
    assert len(api.rows("t1")) == 1


def test_an_unchanged_write_confirms_the_version(api):
    """It keeps the version and moves only c_cacheUpdated to the write (1b)."""
    api.put("t1", objName="A", c_validNotBefore=PAST)
    [before] = api.rows("t1")
    assert api.put("t1", objName="A").json() == {"message": "No changes detected"}
    [after] = api.rows("t1")
    assert after["cache_updated"] > before["cache_updated"]
    assert after["sys_period"] == before["sys_period"]
    assert after["cache_created"] == before["cache_created"]
    assert api.list().json()[0]["c_cacheUpdated"] != api_text(before["cache_updated"])


def test_an_unchanged_write_confirms_only_what_it_repeats(api):
    """1a: a PUT from now on does not confirm the past.

    stored:  A [2020 -> 2099)   B [2099 ->
    PUT B    [2099 ->           -> only B is confirmed
    """
    api.put("t1", objName="A", c_validNotBefore=PAST)
    api.put("t1", objName="B", c_validNotBefore=FUTURE)
    a_before, b_before = api.current("t1")
    api.put("t1", objName="B", c_validNotBefore=FUTURE)
    a_after, b_after = api.current("t1")
    assert a_after["cache_updated"] == a_before["cache_updated"]
    assert b_after["cache_updated"] > b_before["cache_updated"]


def test_an_unchanged_patch_confirms_the_version(api):
    """1c: PATCH is treated like PUT."""
    api.put("t1", objName="A", description="same", c_validNotBefore=PAST)
    [before] = api.rows("t1")
    api.patch("t1", description="same")
    [after] = api.rows("t1")
    assert after["cache_updated"] > before["cache_updated"]


def test_resending_backend_cache_terms_is_no_change(api):
    api.put("t1", objName="Trafo 1")
    api.put("t1", objName="Trafo 1", c_cacheUpdated=FUTURE)
    assert len(api.rows("t1")) == 1


def test_new_source_dates_alone_are_a_change(api):
    api.put("t1", objName="Trafo 1", c_modified=PAST)
    answer = api.put("t1", objName="Trafo 1", c_modified=MIDDLE)
    assert answer.json() == {"message": "Node updated successfully"}
    assert [row["src_modified"] for row in api.current("t1")][-1] == utc(MIDDLE)


def test_a_document_valid_since_the_past_is_not_split_by_a_resend(api):
    """
    stored:  A [2020 ->
    PUT A    (no valid time = [now ->, already known)
    result:  unchanged
    """
    api.put("t1", objName="A", c_validNotBefore=PAST)
    assert api.put("t1", objName="A").json() == {"message": "No changes detected"}
    assert len(api.rows("t1")) == 1


# --- PUT: changing a portion of the valid time ----------------------------------------


def test_a_change_from_now_on_keeps_the_past_and_the_history(api):
    """
    stored:  A [2020 ->
    PUT B    [now ->
    now:     A [2020 -> now)   B [now ->
    history: A [2020 ->        (system time ended)
    """
    api.put("t1", objName="A", c_validNotBefore=PAST)
    answer = api.put("t1", objName="B")
    assert answer.json() == {"message": "Node updated successfully"}

    current = api.current("t1")
    assert [name_of(row) for row in current] == ["A", "B"]
    a_now, b_now = current
    assert valid(a_now)[0] == PAST and valid(a_now)[1] == valid(b_now)[0]
    assert valid(b_now)[1] is None
    # the two rows were recorded in the same instant that ended the old one
    [retired] = [row for row in api.rows("t1") if not row["current"]]
    assert valid(retired) == (PAST, None)
    assert retired["sys_period"].upper == a_now["sys_period"].lower == b_now["sys_period"].lower

    assert api.get("t1", at="2021-01-01T00:00:00Z").json()["product:objName"] == "A"
    assert api.get("t1").json()["product:objName"] == "B"


def test_a_planned_change_does_not_touch_the_present(api):
    """
    stored:  A [2020 ->
    PUT B    [2099 ->
    now:     A [2020 -> 2099)   B [2099 ->
    """
    api.put("t1", objName="A", c_validNotBefore=PAST)
    api.put("t1", objName="B", c_validNotBefore=FUTURE)

    assert [(name_of(r), valid(r)) for r in api.current("t1")] == [
        ("A", (PAST, FUTURE)),
        ("B", (FUTURE, None)),
    ]
    assert api.get("t1").json()["product:objName"] == "A"
    assert api.get("t1", at="2099-06-01T00:00:00Z").json()["product:objName"] == "B"


def test_a_change_in_the_middle_splits_the_document(api):
    """
    stored:  A [2020 ->
    PUT B    [2030 -> 2099)
    now:     A [2020 -> 2030)   B [2030 -> 2099)   A [2099 ->
    """
    api.put("t1", objName="A", c_validNotBefore=PAST)
    api.put("t1", objName="B", c_validNotBefore=MIDDLE, c_validNotAfter=FUTURE)
    assert [(name_of(r), valid(r)) for r in api.current("t1")] == [
        ("A", (PAST, MIDDLE)),
        ("B", (MIDDLE, FUTURE)),
        ("A", (FUTURE, None)),
    ]


def test_first_cached_survives_every_version(api):
    api.put("t1", objName="A", c_validNotBefore=PAST)
    [first] = api.rows("t1")
    api.put("t1", objName="B")
    assert {row["cache_created"] for row in api.current("t1")} == {first["cache_created"]}
    assert all(row["cache_updated"] > first["cache_updated"] for row in api.current("t1"))


# --- PUT: rejected input ----------------------------------------------------------------


def test_an_unknown_cache_term_is_rejected(api):
    answer = api.put("t1", objName="A", c_expire=FUTURE)
    assert answer.status_code == 422
    assert "c_expire" in answer.json()["detail"]
    assert api.rows("t1") == []


def test_a_cache_term_written_as_an_iri_is_rejected(api):
    answer = api.put("t1", **{"objName": "A", "product:c_created": PAST})
    assert answer.status_code == 422
    assert "c_created" in answer.json()["detail"]


def test_a_valid_time_that_ends_before_it_starts_is_rejected(api):
    answer = api.put("t1", objName="A", c_validNotBefore=FUTURE, c_validNotAfter=PAST)
    assert answer.status_code == 422


def test_the_id_must_belong_to_the_path(api):
    body = {"json": api.document("other", objName="A"), "aspect": "product"}
    answer = api.client.put(api.path("t1"), json=body)
    assert answer.status_code == 422
    assert "does not belong to the path" in answer.json()["detail"]


def test_the_aspect_must_match_the_path_segment(api):
    body = {"json": api.document("t1", objName="A"), "aspect": "location"}
    answer = api.client.put(api.path("t1"), json=body)
    assert answer.status_code == 422
    assert "does not match the path segment" in answer.json()["detail"]


def test_id_and_context_are_required(api):
    answer = api.client.put(api.path("t1"), json={"json": {"objName": "A"}, "aspect": "product"})
    assert answer.status_code == 406


# --- PATCH --------------------------------------------------------------------------------


def test_patch_changes_fields_of_the_version_valid_now(api):
    api.put("t1", objName="A", description="old", c_created=PAST, c_validNotBefore=PAST)
    answer = api.patch("t1", description="new")
    assert answer.json() == {"message": "Node updated successfully"}

    a_before, a_now = api.current("t1")
    assert a_before["json"]["description"] == "old"
    assert a_now["json"] == {**a_before["json"], "description": "new"}
    assert a_now["src_created"] == utc(PAST)  # kept from the patched version


def test_patch_with_known_values_changes_nothing(api):
    api.put("t1", objName="A", description="same", c_validNotBefore=PAST)
    assert api.patch("t1", description="same").json() == {"message": "No changes detected"}


def test_patch_without_a_valid_version_is_not_found(api):
    api.put("t1", objName="A", c_validNotBefore=FUTURE)
    assert api.patch("t1", description="x").status_code == 404
    assert api.patch("missing", description="x").status_code == 404


def test_patch_of_a_planned_version(api):
    """
    stored:  A [2020 -> 2099)   B [2099 ->
    PATCH    description=x for [2099 ->
    now:     A unchanged, B gets the description
    """
    api.put("t1", objName="A", c_validNotBefore=PAST)
    api.put("t1", objName="B", c_validNotBefore=FUTURE)
    api.patch("t1", description="x", c_validNotBefore=FUTURE)
    a, b = api.current("t1")
    assert "description" not in a["json"]
    assert b["json"]["objName"] == "B" and b["json"]["description"] == "x"


def test_patch_without_valid_time_writes_from_now_on_over_planned_versions(api):
    """Like a PUT, a PATCH without valid time applies to [now -> and replaces what
    was planned for later.

    stored:  A [2020 -> 2099)   B [2099 ->
    PATCH    description=x      (base: A, the version valid now)
    now:     A [2020 -> now)    A+x [now ->
    """
    api.put("t1", objName="A", c_validNotBefore=PAST)
    api.put("t1", objName="B", c_validNotBefore=FUTURE)
    api.patch("t1", description="x")
    assert [(name_of(r), r["json"].get("description")) for r in api.current("t1")] == [
        ("A", None),
        ("A", "x"),
    ]


# --- DELETE -----------------------------------------------------------------------------


def test_delete_ends_the_document_from_now_on(api):
    api.put("t1", objName="A", c_validNotBefore=PAST)
    answer = api.delete("t1")
    assert answer.json() == {"message": "Node deleted successfully"}
    assert api.get("t1").status_code == 404
    assert api.get("t1", at="2021-01-01T00:00:00Z").status_code == 200


def test_delete_of_a_period_leaves_a_hole(api):
    api.put("t1", objName="A", c_validNotBefore=PAST)
    api.delete("t1", c_validNotBefore=MIDDLE, c_validNotAfter=FUTURE)
    assert [valid(r) for r in api.current("t1")] == [(PAST, MIDDLE), (FUTURE, None)]
    assert api.get("t1", at="2050-01-01T00:00:00Z").status_code == 404


def test_ending_the_validity_is_a_delete_of_the_time_after(api):
    """A PUT names what holds in its period; it never shortens a version.

    stored:  A [2020 ->
    PUT A    [2020 -> 2099)     -> no change, A is known for that period
    DELETE   [2099 ->           -> A [2020 -> 2099)
    """
    api.put("t1", objName="A", c_validNotBefore=PAST)
    shorter = api.put("t1", objName="A", c_validNotBefore=PAST, c_validNotAfter=FUTURE)
    assert shorter.json() == {"message": "No changes detected"}
    api.delete("t1", c_validNotBefore=FUTURE)
    assert [valid(r) for r in api.current("t1")] == [(PAST, FUTURE)]


def test_delete_ends_every_context_of_the_document(api):
    api.put("t1", objName="A")
    body = {
        "json": {**api.document("t1", objName="L"), "@context": api.context("location")},
        "aspect": "product",
    }
    assert api.client.put(api.path("t1"), json=body).status_code == 201
    api.delete("t1")
    assert api.get("t1").status_code == 404
    # both contexts keep only the time before the delete
    current = api.current("t1")
    assert len(current) == 2 and all(row["valid_period"].upper for row in current)


def test_delete_accepts_only_valid_time_in_its_body(api):
    api.put("t1", objName="A")
    answer = api.delete("t1", objName="x")
    assert answer.status_code == 422


def test_delete_of_nothing_is_not_found(api):
    assert api.delete("missing").status_code == 404
    api.put("t1", objName="A", c_validNotBefore=FUTURE)
    assert api.delete("t1", c_validNotAfter=MIDDLE).status_code == 404
