"""JSON-LD document loader and the HTTP answer to JSON-LD errors.

A local HTTP server stands in for the schema service and counts the requests.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar

import pytest
from fastapi import HTTPException
from pyld.jsonld import JsonLdError

CONTEXT = {"@context": {"name": "https://example.org/name"}}


class _Handler(BaseHTTPRequestHandler):
    requests: ClassVar[list[str]] = []

    def do_GET(self):
        type(self).requests.append(self.path)
        if self.path == "/ctx.jsonld":
            body, status, ctype = json.dumps(CONTEXT).encode(), 200, "application/ld+json"
        elif self.path == "/limited.jsonld":
            # what the proxy answers when its rate limit is exhausted
            body, status, ctype = b"Too Many Requests", 429, "text/plain"
        else:
            body, status, ctype = b"404 page not found", 404, "text/plain"
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def server():
    _Handler.requests = []
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


@pytest.fixture
def processor(monkeypatch):
    """A fresh processor and loader, as in a new worker process."""
    from ifdd.be.core import jsonld as module
    from ifdd.be.core.config import reset_settings

    reset_settings()
    monkeypatch.setattr(module, "_processor", None)
    monkeypatch.setattr(module, "_loader_installed", False)
    return module.get_processor()


def _expand(processor, url):
    return processor.expand({"@context": url, "name": "x"}, options=None)


def test_a_context_is_fetched_once_for_many_documents(server, processor):
    for _ in range(5):
        assert _expand(processor, f"{server}/ctx.jsonld")
    assert _Handler.requests == ["/ctx.jsonld"]


def test_an_http_error_is_not_parsed_as_json(server, processor):
    with pytest.raises(JsonLdError) as caught:
        _expand(processor, f"{server}/limited.jsonld")
    from ifdd.be.core.db.session import jsonld_http_error

    answer = jsonld_http_error(caught.value)
    assert answer.status_code == 502
    assert "429" in answer.detail
    assert f"{server}/limited.jsonld" in answer.detail


async def test_get_db_answers_502_when_a_context_cannot_be_fetched():
    from ifdd.be.core.db.session import get_db

    err = JsonLdError(
        "Dereferencing a URL did not result in a valid JSON-LD object.",
        "jsonld.InvalidUrl",
        {"url": "https://schema/v1/organisation.jsonld"},
        code="loading remote context failed",
    )
    db = get_db()
    await db.__anext__()
    with pytest.raises(HTTPException) as caught:
        await db.athrow(err)
    assert caught.value.status_code == 502
    assert "https://schema/v1/organisation.jsonld" in caught.value.detail


async def test_get_db_answers_422_for_an_unusable_document():
    from ifdd.be.core.db.session import get_db

    err = JsonLdError("Invalid JSON-LD syntax.", "jsonld.SyntaxError", code="invalid local context")
    db = get_db()
    await db.__anext__()
    with pytest.raises(HTTPException) as caught:
        await db.athrow(err)
    assert caught.value.status_code == 422
    assert "invalid local context" in caught.value.detail
