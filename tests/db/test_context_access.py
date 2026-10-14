"""Access to domain contexts through the REST API.

Base and aspect contexts are readable with the node read role; a domain
context also needs a matching context pattern. With auth off, the
development user has one pattern, IFDD_CONTEXT_ROOT, so each test picks the
client it needs by that setting:

* ``ifdd.de``               -- sees both test domains (the default)
* ``grid.example.ifdd.de``  -- sees the breaker domain only
* ``none.invalid``          -- sees no domain context
"""

import pytest
from pyld import jsonld

BREAKER = "breaker.grid.example.ifdd.de"
MAINTENANCE = "maintenance.ops.example.ifdd.de"
GRID_ONLY = {"IFDD_CONTEXT_ROOT": "grid.example.ifdd.de"}
NO_DOMAIN = {"IFDD_CONTEXT_ROOT": "none.invalid"}


def put_in(api, uid: str, context: str, **fields):
    """Write the context ``context`` (a name) of the product ``uid``."""
    document = {"@context": api.context(context), "@id": api.node_id(uid), **fields}
    return api.client.put(api.path(uid), json={"json": document, "aspect": "product"})


@pytest.fixture
def breaker(api):
    """A product with its aspect context and both domain contexts."""
    assert api.put("b1", objName="Breaker 1", objType="breaker").status_code == 201
    assert put_in(api, "b1", BREAKER, objName="Q1", serialNumber="SN-1").status_code == 201
    assert put_in(api, "b1", MAINTENANCE, objName="Q1 maint", objType="inspected",
                  lastInspection="2026-01-15").status_code == 201
    return api


# --- reading ---------------------------------------------------------------------------


def test_all_contexts_of_a_node_with_a_matching_root(breaker):
    document = breaker.get("b1").json()
    assert document["product:objName"] == "Breaker 1"
    assert document[f"{BREAKER}:serialNumber"] == "SN-1"
    assert f"{MAINTENANCE}:lastInspection" in document
    assert document["@context"] == {
        "product": "https://type.test/v1/product/",
        BREAKER: f"https://type.test/v1/{BREAKER}/",
        MAINTENANCE: f"https://type.test/v1/{MAINTENANCE}/",
    }


def test_the_answer_is_json_ld_that_expands_again(breaker):
    """The compacted answer expands to the expanded answer (any JSON-LD processor)."""
    compacted = breaker.get("b1").json()
    expanded = breaker.get("b1", **{"json-ld-expanded": "true"}).json()
    assert jsonld.expand(compacted) == jsonld.expand(expanded)
    assert f"https://type.test/v1/{BREAKER}/c_cacheUpdated" in expanded


def test_a_single_document_leaves_out_contexts_without_a_pattern(breaker, make_api):
    with make_api(**GRID_ONLY) as api:
        document = api.get("b1").json()
    assert set(document["@context"]) == {"product", BREAKER}
    assert not any(key.startswith(MAINTENANCE) for key in document)


def test_base_and_aspect_contexts_need_no_pattern(breaker, make_api):
    with make_api(**NO_DOMAIN) as api:
        document = api.get("b1").json()
    assert set(document["@context"]) == {"product"}


def test_a_node_with_only_foreign_domain_contexts_is_forbidden(api, make_api):
    assert put_in(api, "m1", MAINTENANCE, objName="only maintenance").status_code == 201
    with make_api(**GRID_ONLY) as restricted:
        answer = restricted.get("m1")
    assert answer.status_code == 403  # not 404: no security by obscurity
    assert MAINTENANCE in answer.json()["detail"]


def test_lists_and_distinct_values_leave_out_foreign_domains(breaker, make_api):
    with make_api(**GRID_ONLY) as api:
        all_nodes = api.client.get("/nodes/")
        names = sorted(entry["objName"] for entry in all_nodes.json())
        assert names == ["Breaker 1", "Q1"]
        assert all_nodes.headers["X-Total-Count"] == "2"
        types = sorted(entry["@id"] for entry in api.client.get("/types").json())
        assert types == ["breaker"]  # "inspected" exists only in the maintenance context


def test_listing_a_domain_context_explicitly(breaker, make_api):
    with make_api(**GRID_ONLY) as api:
        mine = api.list(context=api.context(BREAKER))
        assert [entry["serialNumber"] for entry in mine.json()] == ["SN-1"]
        foreign = api.list(context=api.context(MAINTENANCE))
        assert foreign.status_code == 403
        assert api.list(context="https://elsewhere.example/v1/x.y.jsonld").status_code == 422


def test_the_aspect_list_shows_the_aspect_context_only(breaker):
    assert [entry["objName"] for entry in breaker.list().json()] == ["Breaker 1"]


def test_the_graph_uses_base_and_aspect_contexts_only(breaker):
    """Labels come from objName of the generic contexts, never from a domain."""
    graph = breaker.client.post("/graph_data", json={"ids": [breaker.node_id("b1")]}).json()
    assert [entry["data"]["label"] for entry in graph] == ["Breaker 1"]


# --- writing ---------------------------------------------------------------------------


def test_writing_needs_a_matching_pattern(api, make_api):
    with make_api(**GRID_ONLY) as restricted:
        assert put_in(restricted, "w1", BREAKER, objName="mine").status_code == 201
        refused = put_in(restricted, "w1", MAINTENANCE, objName="foreign")
        assert refused.status_code == 403
        assert restricted.put("w1", objName="aspect").status_code == 201  # no pattern needed
    assert {row["json"]["objName"] for row in api.current("w1")} == {"mine", "aspect"}


@pytest.mark.parametrize(
    "context, reason",
    [
        ("nocache.grid.example.ifdd.de", "does not define the term 'c_created'"),
        ("slashless.grid.example.ifdd.de", "must end with '/' or '#'"),
        ("maint", "neither base, an aspect"),
    ],
)
def test_contexts_that_do_not_qualify_are_refused(api, context, reason):
    answer = put_in(api, "x1", context, objName="X")
    assert answer.status_code == 422
    assert reason in answer.json()["detail"]


def test_a_context_from_elsewhere_is_refused(api):
    document = {"@context": "https://elsewhere.example/v1/product.jsonld",
                "@id": api.node_id("x2"), "objName": "X"}
    answer = api.client.put(api.path("x2"), json={"json": document, "aspect": "product"})
    assert answer.status_code == 422
    assert "is not below" in answer.json()["detail"]


# --- deleting --------------------------------------------------------------------------


def contexts_of(make_api, uid: str) -> set[str]:
    """The context names of a node as the full client (root ifdd.de) reads them now.

    A fresh client each time: create_app registers its settings globally, so
    a client built before a restricted one would read with the restricted
    pattern.
    """
    with make_api() as full:
        answer = full.get(uid)
        return set(answer.json()["@context"]) if answer.status_code == 200 else set()


def test_delete_ends_every_context_only_if_all_may_be_written(breaker, make_api):
    with make_api(**GRID_ONLY) as restricted:
        assert restricted.delete("b1").status_code == 403
    assert contexts_of(make_api, "b1") == {"product", BREAKER, MAINTENANCE}  # nothing ended
    with make_api() as full:
        assert full.delete("b1").status_code == 200
    assert contexts_of(make_api, "b1") == set()


def test_delete_of_one_context(breaker, make_api):
    with make_api(**GRID_ONLY) as restricted:
        path = restricted.path("b1")
        answer = restricted.client.request(
            "DELETE", path, params={"context": restricted.context(BREAKER)}
        )
        assert answer.status_code == 200
        foreign = restricted.client.request(
            "DELETE", path, params={"context": restricted.context(MAINTENANCE)}
        )
        assert foreign.status_code == 403
    assert contexts_of(make_api, "b1") == {"product", MAINTENANCE}
