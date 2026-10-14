"""Token validation and role checks with auth enabled.

Tokens are signed with a throwaway RSA key; the JWKS lookup is replaced so
that no identity provider is needed. Database access is replaced by a stub
that answers 418, which shows that a request got past authentication.
"""
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fastapi.testclient import TestClient

ISSUER = "https://id.example.org/realms/ifddtest"
AUDIENCE = "ifddtest"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class _SigningKey:
    key = KEY.public_key()


class _FakeJWKClient:
    def __init__(self, *args, **kwargs):
        pass

    def get_signing_key_from_jwt(self, token):
        return _SigningKey()


def token(roles=(), typ="Bearer", iss=ISSUER, aud=AUDIENCE, key=KEY):
    now = int(time.time())
    claims = {"iss": iss, "aud": aud, "sub": "user-1", "iat": now, "exp": now + 300,
              "preferred_username": "tester",
              "resource_access": {AUDIENCE: {"roles": list(roles)}}}
    if typ is not None:
        claims["typ"] = typ
    return jwt.encode(claims, key, algorithm="RS256")


def bearer(t):
    return {"Authorization": f"Bearer {t}"}


async def _db_reached():
    raise HTTPException(status_code=418, detail="database reached")
    yield  # pragma: no cover


@pytest.fixture
def secured(monkeypatch):
    from ifdd.be.core import create_app
    from ifdd.be.core.auth import oidc
    from ifdd.be.core.config import CoreSettings, reset_settings
    from ifdd.be.core.db import session as db_session

    monkeypatch.setattr(oidc, "PyJWKClient", _FakeJWKClient)
    monkeypatch.setattr(oidc, "_scheme", None)
    monkeypatch.setattr(oidc, "_token_cache", None)
    reset_settings()
    settings = CoreSettings(
        IFDD_BE_AUTH_ENABLED=True,
        IFDD_OIDC_JWKS_URL="https://id.example.org/certs",
        IFDD_OIDC_TOKEN_URL="https://id.example.org/token",
        IFDD_OIDC_AUTHORIZATION_URL="https://id.example.org/auth",
        IFDD_OIDC_REFRESH_URL="https://id.example.org/token",
        IFDD_OIDC_JWKS_AUDIENCE=AUDIENCE,
        IFDD_OIDC_ISSUER=ISSUER,
    )
    app = create_app(settings)
    app.dependency_overrides[db_session.get_db] = _db_reached
    with TestClient(app) as client:
        yield client
    reset_settings()


# --- what counts as a valid access token -------------------------------------

def test_access_token_with_public_role_is_accepted(secured):
    r = secured.get("/prot_version", headers=bearer(token(["ifdd_public"])))
    assert r.status_code == 200, r.text


@pytest.mark.parametrize("typ", ["ID", "Refresh", None])
def test_other_token_types_are_rejected(secured, typ):
    # an ID token of the same client carries the same audience and roles
    r = secured.get("/prot_version", headers=bearer(token(["ifdd_public"], typ=typ)))
    assert r.status_code == 401
    assert "not an access token" in r.json()["detail"]


def test_wrong_issuer_is_rejected(secured):
    r = secured.get("/prot_version",
                    headers=bearer(token(["ifdd_public"], iss="https://id.example.org/realms/other")))
    assert r.status_code == 401


def test_wrong_audience_is_rejected(secured):
    r = secured.get("/prot_version", headers=bearer(token(["ifdd_public"], aud="other")))
    assert r.status_code == 401


def test_foreign_signature_is_rejected(secured):
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    r = secured.get("/prot_version", headers=bearer(token(["ifdd_public"], key=other)))
    assert r.status_code == 401


def test_missing_token_is_rejected(secured):
    assert secured.get("/prot_version").status_code == 401


# --- roles per endpoint ---------------------------------------------------------

def test_prot_version_needs_the_public_role(secured):
    r = secured.get("/prot_version", headers=bearer(token(["ifdd_nodes_ro"])))
    assert r.status_code == 403


NODE = {"json": {"@id": "urn:x", "@context": {}}, "aspect": "products"}


@pytest.mark.parametrize("method", ["put", "patch"])
def test_writing_needs_the_write_role(secured, method):
    send = getattr(secured, method)
    reader = send("/products/p1", json=NODE, headers=bearer(token(["ifdd_nodes_ro"])))
    assert reader.status_code == 403, reader.text
    writer = send("/products/p1", json=NODE, headers=bearer(token(["ifdd_nodes_ro", "ifdd_nodes_rw"])))
    assert writer.status_code == 418, writer.text          # got past authentication


def test_graph_data_needs_the_read_role(secured):
    body = {"ids": ["urn:x"]}
    assert secured.post("/graph_data", json=body).status_code == 401
    assert secured.post("/graph_data", json=body, headers=bearer(token(["ifdd_public"]))).status_code == 403
    assert secured.post("/graph_data", json=body, headers=bearer(token(["ifdd_nodes_ro"]))).status_code == 418


def test_reading_needs_the_read_role(secured):
    assert secured.post("/types", headers=bearer(token(["ifdd_public"]))).status_code == 403
    assert secured.post("/types", headers=bearer(token(["ifdd_nodes_ro"]))).status_code == 418


# --- auth switched off (development) ---------------------------------------------

def test_dev_user_has_all_roles(client):
    from ifdd.be.core.config import get_settings

    s = get_settings()
    roles = client.get("/whoami").json()["client_roles"]
    for role in (s.IFDD_ROLE_PUBLIC, s.IFDD_ROLE_NODES_READ, s.IFDD_ROLE_NODES_WRITE):
        assert role in roles


# --- /version, /prot_version and /whoami with auth enabled ------------------------

def test_version_needs_no_token(secured):
    r = secured.get("/version")
    assert r.status_code == 200, r.text


def test_prot_version_answer_is_unchanged(secured):
    # ifdd-ui shows this answer on its dashboard (src/Dashboard.jsx).
    from ifdd.be.core.config import get_settings

    r = secured.get("/prot_version", headers=bearer(token(["ifdd_public"])))
    assert r.json() == {"version": f"{get_settings().IFDD_BE_VERSION}_prot"}


def test_whoami_needs_a_token_but_no_role(secured):
    assert secured.get("/whoami").status_code == 401
    r = secured.get("/whoami", headers=bearer(token([])))
    assert r.status_code == 200, r.text
    assert r.json() == {"preferred_username": "tester", "client_roles": [], "context_patterns": []}


def test_whoami_splits_roles_and_context_patterns(secured):
    roles = ["ifdd_public", "ifdd_nodes_ro", "Grid.Example.ifdd.de", "ifdd.de", "ifdd_nodes_rw"]
    r = secured.get("/whoami", headers=bearer(token(roles)))
    assert r.status_code == 200, r.text
    assert r.json() == {
        "preferred_username": "tester",
        "client_roles": ["ifdd_nodes_ro", "ifdd_nodes_rw", "ifdd_public"],
        # lower-case, as the backend compares them (contexts.Access)
        "context_patterns": ["grid.example.ifdd.de", "ifdd.de"],
    }


def test_whoami_rejects_an_id_token(secured):
    r = secured.get("/whoami", headers=bearer(token(["ifdd_public"], typ="ID")))
    assert r.status_code == 401
