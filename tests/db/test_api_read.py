"""Reading through the REST API: one instant in valid time (``at``), default now.

Every read sees what the backend knows now (current system time) and is valid
at that instant, so each document appears at most once per context.
"""

import pytest

PAST = "2020-01-01T00:00:00+00:00"
FUTURE = "2099-01-01T00:00:00+00:00"


def names(answer) -> list[str]:
    return [entry["objName"] for entry in answer.json()]


# --- lists ---------------------------------------------------------------------------


def test_a_list_entry_carries_its_cache_terms_as_plain_terms(api):
    api.put("t1", objName="A", c_created=PAST, c_validNotBefore=PAST)
    [entry] = api.list().json()
    assert entry["objName"] == "A"
    assert entry["c_created"] == PAST
    assert entry["c_validNotBefore"] == PAST
    assert "c_validNotAfter" not in entry  # open-ended
    assert {"c_cacheCreated", "c_cacheUpdated"} <= set(entry)


def test_a_list_shows_the_versions_valid_at_the_instant(api):
    """
    t1:  A [2020 -> 2099)   B [2099 ->
    t2:                     C [2099 ->
    """
    api.put("t1", objName="A", c_validNotBefore=PAST)
    api.put("t1", objName="B", c_validNotBefore=FUTURE)
    api.put("t2", objName="C", c_validNotBefore=FUTURE)

    assert names(api.list()) == ["A"]
    assert sorted(names(api.list(at="2099-06-01T00:00:00Z"))) == ["B", "C"]
    assert names(api.list(at="2010-01-01T00:00:00Z")) == []


def test_an_instant_without_time_zone_is_utc(api):
    api.put("t1", objName="A", c_validNotBefore="2050-01-01T00:00:00+00:00")
    assert names(api.list(at="2049-12-31T23:59:59")) == []
    assert names(api.list(at="2050-01-01T00:00:00")) == ["A"]


def test_an_invalid_instant_is_rejected(api):
    assert api.list(at="yesterday").status_code == 422


def test_paging_reports_the_total_of_all_matches(api):
    for number in range(5):
        api.put(f"t{number}", objName=f"N{number}")
    page = api.list(start=1, end=3, sort="objName")
    assert names(page) == ["N1", "N2"]
    assert page.headers["X-Total-Count"] == "5"
    past_the_end = api.list(start=10, end=20)
    assert past_the_end.json() == [] and past_the_end.headers["X-Total-Count"] == "5"


@pytest.mark.parametrize(
    "sort, order, expected",
    [
        ("c_created", "ASC", ["old", "middle", "new"]),
        ("c_created", "DESC", ["new", "middle", "old"]),
        ("objName", "ASC", ["middle", "new", "old"]),  # a document field, indexed too
        ("c_cacheUpdated", "ASC", ["middle", "new", "old"]),  # write order
    ],
)
def test_sorting(api, sort, order, expected):
    api.put("m", objName="middle", c_created="2021-01-01T00:00:00Z")
    api.put("n", objName="new", c_created="2022-01-01T00:00:00Z")
    api.put("o", objName="old", c_created="2020-01-01T00:00:00Z")
    assert names(api.list(sort=sort, order=order)) == expected


def test_sorting_by_type_and_scope(api):
    api.put("t1", objName="A", objType="switch", objScope="lab")
    api.put("t2", objName="B", objType="cable", objScope="grid")
    assert names(api.list(sort="objType")) == ["B", "A"]
    assert names(api.list(sort="objScope", order="DESC")) == ["A", "B"]


def test_an_unknown_sort_key_is_refused(api):
    """Only keys with an index are offered (decision 3, list B)."""
    answer = api.list(sort="description")
    assert answer.status_code == 422
    assert api.list(sort="name").status_code == 422


def test_the_default_order_is_by_cache_updated(api):
    for name in ("first", "second", "third"):
        api.put(name, objName=name)
    assert names(api.list()) == ["first", "second", "third"]


def test_filters_by_type_and_scope(api):
    api.put("t1", objName="A", objType="trafo", objScope="grid")
    api.put("t2", objName="B", objType="line", objScope="grid")
    api.put("t3", objName="C", objType="trafo", objScope="lab")
    assert names(api.list(type_id="trafo")) == ["A", "C"]
    assert names(api.list(type_id="trafo", scope_id="grid")) == ["A"]


def test_a_list_restricted_to_ids(api):
    for uid in ("t1", "t2", "t3"):
        api.put(uid, objName=uid)
    ids = [api.node_id("t1"), api.node_id("t3")]
    answer = api.client.post("/products", json={"ids": ids})
    assert names(answer) == ["t1", "t3"]


def test_search_finds_text_anywhere_in_the_document(api):
    api.put("t1", objName="Trafo Nord", description="110 kV")
    api.put("t2", objName="Trafo Sued", description="50% load")
    assert names(api.list(query="Nord")) == ["Trafo Nord"]
    assert names(api.list(query="110 kV")) == ["Trafo Nord"]
    # LIKE wildcards in the search text are literal
    assert names(api.list(query="50%")) == ["Trafo Sued"]
    assert names(api.list(query="5_%")) == []


def test_search_respects_the_instant(api):
    api.put("t1", objName="Old name", c_validNotBefore=PAST)
    api.put("t1", objName="New name", c_validNotBefore=FUTURE)
    assert names(api.list(query="name")) == ["Old name"]
    assert names(api.list(query="New")) == []


def test_all_nodes_list(api):
    api.put("t1", objName="A")
    location = {"json": api.document("l1", aspect="location", objName="L"), "aspect": "location"}
    api.client.put(api.path("l1", aspect="location"), json=location)
    answer = api.client.get("/nodes/")
    assert sorted(names(answer)) == ["A", "L"]
    assert answer.headers["X-Total-Count"] == "2"


# --- single documents ------------------------------------------------------------------


def test_a_single_document_has_its_cache_terms_in_its_namespace(api):
    api.put("t1", objName="A", c_created=PAST, c_validNotBefore=PAST)
    document = api.get("t1").json()
    assert document["product:objName"] == "A"
    assert document["product:c_created"]["@value"] == PAST
    assert document["product:c_validNotBefore"]["@value"] == PAST
    assert "product:c_cacheUpdated" in document
    assert "product:c_validNotAfter" not in document
    # the prefix is the context name, mapped to its namespace (expandable JSON-LD)
    assert document["@context"] == {"product": "https://type.test/v1/product/"}


def test_the_expanded_form_on_request(api):
    api.put("t1", objName="A")
    expanded = api.get("t1", **{"json-ld-expanded": "true"}).json()
    assert expanded["https://type.test/v1/product/objName"] == [{"@value": "A"}]
    assert "https://type.test/v1/product/c_cacheUpdated" in expanded


def test_a_document_in_two_contexts_keeps_both_sets_of_cache_terms(api):
    """Every c_* value stays apart by the namespace of its context (C5)."""
    api.put("t1", objName="A", c_created=PAST)
    as_location = {
        "json": {**api.document("t1", objName="L"), "@context": api.context("location")},
        "aspect": "product",
    }
    api.client.put(api.path("t1"), json=as_location)

    document = api.get("t1").json()
    assert document["product:objName"] == "A" and document["location:objName"] == "L"
    assert document["product:c_created"]["@value"] == PAST
    assert "location:c_created" not in document
    assert "product:c_cacheUpdated" in document and "location:c_cacheUpdated" in document
    assert set(document["@context"]) == {"product", "location"}


def test_a_single_document_at_an_instant(api):
    api.put("t1", objName="A", c_validNotBefore=PAST)
    api.put("t1", objName="B", c_validNotBefore=FUTURE)
    assert api.get("t1").json()["product:objName"] == "A"
    assert api.get("t1", at="2099-01-01T00:00:00Z").json()["product:objName"] == "B"
    assert api.get("t1", at="2019-12-31T23:59:59Z").status_code == 404


def test_the_lookup_ignores_the_query_string(api):
    """Up to 26.10.2 the lookup used the full URL, query string included."""
    api.put("t1", objName="A")
    assert api.client.get(api.path("t1") + "?unrelated=1").status_code == 200


def test_an_unknown_document_is_not_found(api):
    assert api.get("missing").status_code == 404


# --- distinct values and graph -------------------------------------------------------


def test_types_and_scopes_at_an_instant(api):
    api.put("t1", objName="A", objType="trafo", objScope="grid", c_validNotBefore=PAST)
    api.put("t1", objName="A", objType="switch", objScope="grid", c_validNotBefore=FUTURE)
    api.put("t2", objName="B", objType="line", objScope="lab")

    def values(path, **params):
        return sorted(entry["@id"] for entry in api.client.get(path, params=params).json())

    assert values("/types") == ["line", "trafo"]
    assert values("/types", at="2099-06-01T00:00:00Z") == ["line", "switch"]
    assert values("/scopes") == ["grid", "lab"]


def test_graph_data_follows_links_valid_at_the_instant(api):
    location = api.node_id("l1", aspect="location")
    api.put("t1", objName="A", containedIn=location)
    body = {"json": api.document("l1", aspect="location", objName="Site"), "aspect": "location"}
    api.client.put(api.path("l1", aspect="location"), json=body)

    graph = api.client.post("/graph_data", json={"ids": [api.node_id("t1")]}).json()
    node_ids = {entry["data"]["id"] for entry in graph if "id" in entry["data"]}
    edges = [entry["data"] for entry in graph if "source" in entry["data"]]
    assert node_ids == {api.node_id("t1"), location}
    assert edges[0]["label"] == "containedIn"

    before = api.client.post(
        "/graph_data", json={"ids": [api.node_id("t1")]}, params={"at": "2000-01-01T00:00:00Z"}
    ).json()
    assert before == []
