"""The documentation pages and the OpenAPI document.

The pages must work under the proxy's Content-Security-Policy for the
backend (no inline script, no inline style, nothing from other hosts); the
first group of tests checks exactly that. FastAPI's own pages fail it: their
/docs and /docs/oauth2-redirect start Swagger UI with inline scripts and load
it from a CDN.
"""

from __future__ import annotations

from html.parser import HTMLParser

import pytest
from fastapi.testclient import TestClient

PAGES = ["/docs", "/docs/oauth2-redirect", "/redoc"]


class _Page(HTMLParser):
    """Collects what a CSP without 'unsafe-inline' and without other hosts forbids."""

    def __init__(self):
        super().__init__()
        self.inline_scripts: list[str] = []
        self.style_elements = 0
        self.inline_handlers: list[str] = []
        self.style_attributes: list[str] = []
        self.urls: list[str] = []
        self._in_script = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        for name in attrs:
            if name.startswith("on"):
                self.inline_handlers.append(f"{tag}[{name}]")
        if "style" in attrs:
            self.style_attributes.append(tag)
        if tag == "style":
            self.style_elements += 1
        if tag == "script":
            self._in_script = "src" not in attrs
        for name in ("src", "href", "spec-url"):
            if name in attrs:
                self.urls.append(attrs[name])
        for name, value in attrs.items():
            if name.endswith("-url") and name.startswith("data-"):
                self.urls.append(value)

    def handle_endtag(self, tag):
        if tag == "script":
            self._in_script = False

    def handle_data(self, data):
        if self._in_script and data.strip():
            self.inline_scripts.append(data.strip()[:60])


def parse(html: str) -> _Page:
    page = _Page()
    page.feed(html)
    return page


@pytest.fixture
def secured_app():
    from ifdd.be.core import create_app
    from ifdd.be.core.config import CoreSettings, reset_settings

    reset_settings()
    app = create_app(
        CoreSettings(
            IFDD_BE_AUTH_ENABLED=True,
            IFDD_OIDC_JWKS_AUDIENCE="ifddtest",
            IFDD_OIDC_AUTHORIZATION_URL="https://id/realms/ifddtest/protocol/openid-connect/auth",
            IFDD_OIDC_TOKEN_URL="https://id/realms/ifddtest/protocol/openid-connect/token",
            IFDD_OIDC_REFRESH_URL="https://id/realms/ifddtest/protocol/openid-connect/token",
        )
    )
    with TestClient(app) as client:
        yield client
    reset_settings()


# --- pages ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", PAGES)
def test_page_has_no_inline_script_or_style(client, path):
    response = client.get(path)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/html")
    page = parse(response.text)
    assert page.inline_scripts == []
    assert page.inline_handlers == []
    assert page.style_elements == 0
    assert page.style_attributes == []


@pytest.mark.parametrize("path", PAGES)
def test_page_loads_nothing_from_other_hosts(client, path):
    page = parse(client.get(path).text)
    assert page.urls, "the page should reference its assets"
    for url in page.urls:
        assert url.startswith("/"), url
        assert not url.startswith("//"), url


@pytest.mark.parametrize("path", PAGES)
def test_every_referenced_asset_is_served(client, path):
    for url in parse(client.get(path).text).urls:
        if url.startswith("/docs/assets/"):
            response = client.get(url)
            assert response.status_code == 200, url


def test_asset_content_types(client):
    expected = {
        "/docs/assets/swagger-ui/swagger-ui-bundle.js": "javascript",
        "/docs/assets/swagger-ui/oauth2-redirect.js": "javascript",
        "/docs/assets/swagger-ui/swagger-ui.css": "text/css",
        "/docs/assets/redoc/redoc.standalone.js": "javascript",
        "/docs/assets/ifdd/swagger-init.js": "javascript",
        "/docs/assets/ifdd/docs.css": "text/css",
    }
    for url, kind in expected.items():
        response = client.get(url)
        assert response.status_code == 200, url
        assert kind in response.headers["content-type"], (url, response.headers["content-type"])


def test_swagger_page_carries_the_login_values(secured_app):
    html = secured_app.get("/docs").text
    assert 'data-openapi-url="/openapi.json"' in html
    assert 'data-oauth2-redirect-url="/docs/oauth2-redirect"' in html
    assert 'data-client-id="ifddtest"' in html
    assert 'data-scopes="openid profile email"' in html


def test_swagger_page_has_no_login_without_auth(client):
    assert 'data-client-id=""' in client.get("/docs").text


def test_pages_need_no_token(secured_app):
    for path in [*PAGES, "/openapi.json", "/docs/assets/ifdd/swagger-init.js"]:
        assert secured_app.get(path).status_code == 200, path


def test_redirect_page_is_not_taken_by_the_document_route(client):
    # /docs/oauth2-redirect has the shape of GET /{node_aspect}/{node_id}.
    html = client.get("/docs/oauth2-redirect").text
    assert "/docs/assets/swagger-ui/oauth2-redirect.js" in html


def test_root_path_prefixes_every_url():
    from ifdd.be.core import create_app
    from ifdd.be.core.config import CoreSettings, reset_settings

    reset_settings()
    app = create_app(CoreSettings())
    with TestClient(app, root_path="/api") as client:
        for path in PAGES:
            for url in parse(client.get(path).text).urls:
                assert url.startswith("/api/"), (path, url)
    reset_settings()


# --- the OpenAPI document ------------------------------------------------------------


@pytest.fixture
def spec(secured_app):
    return secured_app.get("/openapi.json").json()


def operations(spec):
    for path, item in spec["paths"].items():
        for method, operation in item.items():
            yield path, method, operation


def test_info_names_versions_and_license(spec):
    from ifdd.be.core import __version__
    from ifdd.be.core.config import get_settings

    info = spec["info"]
    assert info["version"] == get_settings().IFDD_BE_VERSION
    assert f"ifdd-be-core` {__version__}" in info["description"]
    assert info["license"] == {"name": "BSD-3-Clause", "identifier": "BSD-3-Clause"}
    assert "contact" not in info
    assert spec["externalDocs"]["url"].startswith("https://github.com/ifdd-de/")


def test_every_tag_is_described(spec):
    described = {tag["name"] for tag in spec["tags"] if tag.get("description")}
    used = {tag for _, _, op in operations(spec) for tag in op.get("tags", [])}
    assert used <= described


def test_every_operation_has_summary_and_description(spec):
    for path, method, op in operations(spec):
        assert op.get("summary"), (method, path)
        assert op.get("description"), (method, path)
        # The developer part after the form feed stays out of the document.
        assert "Args:" not in op["description"], (method, path)
        assert "Returns:" not in op["description"], (method, path)


def test_every_path_parameter_is_declared_and_described(spec):
    import re

    for path, method, op in operations(spec):
        declared = {p["name"] for p in op.get("parameters", []) if p["in"] == "path"}
        assert declared == set(re.findall(r"{(\w+)}", path)), (method, path)
        for parameter in op.get("parameters", []):
            assert parameter.get("description"), (method, path, parameter["name"])


def test_errors_are_documented(spec):
    for path, method, op in operations(spec):
        if path == "/version":
            continue
        assert "401" in op["responses"], (method, path)
    put = spec["paths"]["/{node_aspect}/{node_id}"]["put"]
    for code in ("201", "200", "401", "403", "406", "409", "422", "502"):
        assert code in put["responses"], code
    assert put["requestBody"]["content"]["application/json"]["examples"]


def test_version_is_open_and_the_rest_needs_a_token(spec):
    assert spec["paths"]["/version"]["get"]["security"] == []
    schemes = {name for alternative in spec["security"] for name in alternative}
    assert schemes == {"OAuth2AuthCode", "BearerToken"}
    flow = spec["components"]["securitySchemes"]["OAuth2AuthCode"]["flows"]["authorizationCode"]
    assert flow["authorizationUrl"].endswith("/protocol/openid-connect/auth")


def test_removed_and_kept_endpoints(spec):
    assert "/public" not in spec["paths"]
    assert "/private" not in spec["paths"]
    assert "/whoami" in spec["paths"]
    assert "/prot_version" in spec["paths"]
    assert "/docs" not in spec["paths"]


def test_aspect_routes_of_the_configuration_are_documented(spec):
    from ifdd.be.core.config import get_settings

    for segment in get_settings().IFDD_ASPECTS:
        assert f"/{segment}" in spec["paths"]


def test_get_operations_document_no_body(spec):
    # Browsers cannot send a body with GET; Swagger UI would send nothing.
    for path, method, op in operations(spec):
        if method == "get":
            assert "requestBody" not in op, path
    assert "requestBody" in spec["paths"]["/products"]["post"]
