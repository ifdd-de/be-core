"""Context kinds, names and patterns (no database needed)."""

import pytest

from ifdd.be.core.config import CoreSettings, configure, reset_settings
from ifdd.be.core.contexts import (
    Access,
    ContextError,
    ContextForbidden,
    is_domain_name,
    matches,
    name_of,
    parse,
)

SCHEMA = "https://schema.example/v1"


@pytest.fixture(autouse=True)
def settings():
    configure(CoreSettings(IFDD_SCHEMA_URL=SCHEMA, IFDD_OIDC_JWKS_AUDIENCE="ifddtest"))
    yield
    reset_settings()


@pytest.mark.parametrize("name", ["base", "product", "function", "location", "organisation"])
def test_base_and_aspects_are_generic(name):
    context = parse(f"{SCHEMA}/{name}.jsonld")
    assert (context.name, context.domain, context.domain_name) == (name, False, None)


def test_a_dotted_name_is_a_domain_context():
    context = parse(f"{SCHEMA}/sub1.dom1.ifdd.de.jsonld")
    assert (context.name, context.domain_name) == ("sub1.dom1.ifdd.de", "sub1.dom1.ifdd.de")


def test_the_name_ignores_the_version_path():
    assert parse(f"{SCHEMA}/2/sub1.dom1.ifdd.de.jsonld").name == "sub1.dom1.ifdd.de"


@pytest.mark.parametrize(
    "url, reason",
    [
        ("https://elsewhere.example/v1/sub1.dom1.ifdd.de.jsonld", "is not below"),
        (f"{SCHEMA}/sub1.dom1.ifdd.de", "does not name a .jsonld file"),
        (f"{SCHEMA}/maint.jsonld", "neither base, an aspect"),  # a typo stays private
        (f"{SCHEMA}/Sub1.dom1.ifdd.de.jsonld", "neither base, an aspect"),
        (f"{SCHEMA}/sub_1.dom1.ifdd.de.jsonld", "neither base, an aspect"),
        (f"{SCHEMA}/-sub.dom1.ifdd.de.jsonld", "neither base, an aspect"),
    ],
)
def test_other_contexts_are_refused(url, reason):
    with pytest.raises(ContextError, match=reason):
        parse(url)


def test_domain_names():
    assert is_domain_name("a.b") and is_domain_name("x-1.dom1.ifdd.de")
    assert not is_domain_name("single") and not is_domain_name("a..b")


@pytest.mark.parametrize(
    "name, pattern, expected",
    [
        ("dom1.ifdd.de", "dom1.ifdd.de", True),
        ("sub1.dom1.ifdd.de", "dom1.ifdd.de", True),
        ("sub1.dom1.ifdd.de", "ifdd.de", True),
        ("xdom1.ifdd.de", "dom1.ifdd.de", False),  # label boundary
        ("dom1.ifdd.de", "sub1.dom1.ifdd.de", False),  # never upwards
    ],
)
def test_patterns_match_at_label_boundaries(name, pattern, expected):
    assert matches(name, pattern) is expected


def test_patterns_are_the_client_roles_with_a_dot():
    token = {"resource_access": {"ifddtest": {"roles": ["ifdd_nodes_ro", "Dom1.IFDD.de"]},
                                 "other": {"roles": ["dom2.ifdd.de"]}}}
    access = Access.from_token(token)
    assert access.patterns == ("dom1.ifdd.de",)
    assert access.may_use(None)  # base and aspect contexts
    assert access.may_use("sub1.dom1.ifdd.de")
    assert not access.may_use("sub1.dom2.ifdd.de")
    with pytest.raises(ContextForbidden):
        access.require("sub1.dom2.ifdd.de")


def test_the_example_of_the_concept():
    """Three contexts, three clients (decision of 2026-10-10)."""
    contexts = ["sub1.dom1.ifdd.de", "sub2.dom1.ifdd.de", "sub1.dom2.ifdd.de"]
    clients = {"ifdd.de": [True, True, True],
               "dom1.ifdd.de": [True, True, False],
               "sub1.dom2.ifdd.de": [False, False, True]}
    for pattern, expected in clients.items():
        assert [Access(patterns=(pattern,)).may_use(c) for c in contexts] == expected


def test_name_of_a_stored_url():
    assert name_of(f"{SCHEMA}/product.jsonld") == "product"
    assert name_of("https://old.example/v1/sub1.dom1.ifdd.de.jsonld") == "sub1.dom1.ifdd.de"


async def test_the_development_user_has_the_root_pattern():
    from starlette.requests import Request

    from ifdd.be.core.auth.oidc import optional_auth

    configure(CoreSettings(IFDD_BE_AUTH_ENABLED=False, IFDD_CONTEXT_ROOT="example.ifdd.de",
                           IFDD_OIDC_JWKS_AUDIENCE="ifddtest"))
    data = await optional_auth()(Request({"type": "http", "headers": []}))
    assert Access.from_token(data).patterns == ("example.ifdd.de",)
