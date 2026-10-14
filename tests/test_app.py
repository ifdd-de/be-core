from ifdd.be.core.config import CoreSettings, reset_settings
from ifdd.be.core.routers.aspects import build_aspect_router


def test_public_and_private_are_gone(client):
    # /version is the endpoint without token, /whoami replaces /private.
    assert client.get("/public").status_code == 404
    assert client.get("/private").status_code == 404


def test_version_endpoint(client):
    from ifdd.be.core.config import get_settings

    response = client.get("/version")
    assert response.status_code == 200
    assert response.json() == {"version": get_settings().IFDD_BE_VERSION}


def test_prot_version_keeps_its_answer(client):
    # ifdd-ui shows this answer on its dashboard (src/Dashboard.jsx).
    from ifdd.be.core.config import get_settings

    response = client.get("/prot_version")
    assert response.status_code == 200
    assert response.json() == {"version": f"{get_settings().IFDD_BE_VERSION}_prot"}


def test_whoami_without_auth_shows_the_dev_user(client):
    from ifdd.be.core.config import get_settings

    s = get_settings()
    response = client.get("/whoami")
    assert response.status_code == 200
    assert response.json() == {
        "preferred_username": "dev-user",
        "client_roles": sorted(
            [s.IFDD_ROLE_PUBLIC, s.IFDD_ROLE_NODES_READ, s.IFDD_ROLE_NODES_WRITE]
        ),
        "context_patterns": [s.IFDD_CONTEXT_ROOT],
    }


def test_openapi_declares_oauth_scheme(client):
    schema = client.get("/openapi.json").json()
    assert "OAuth2AuthCode" in schema["components"]["securitySchemes"]


def test_aspect_routes_come_from_configuration():
    reset_settings()
    router = build_aspect_router({"widgets": "widget", "gadgets": "gadget"})
    paths = {route.path for route in router.routes}
    assert paths == {"/widgets", "/gadgets"}


def test_importing_core_does_not_require_a_database():
    reset_settings()
    settings = CoreSettings(IFDD_SERVICE_DB_URL="")
    assert settings.IFDD_SERVICE_DB_URL == ""
