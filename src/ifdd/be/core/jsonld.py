"""Single owner of the JSON-LD processor and its document loader."""

from __future__ import annotations

from typing import Optional

import requests_cache
from pyld import jsonld

from .config import get_settings

_processor: Optional[jsonld.JsonLdProcessor] = None
_loader_installed = False


def _raise_for_status(response, *args, **kwargs):
    """Fail on HTTP errors before PyLD parses an error page as JSON.

    PyLD does not look at the status code: a 404 or 429 would otherwise end as
    "not a valid JSON-LD object", without the status.
    """
    response.raise_for_status()


def install_document_loader() -> None:
    """Give PyLD a document loader with an in-memory cache, once per process.

    Contexts are kept for ``JSONLD_CACHE_EXPIRE_AFTER`` seconds and fetched
    with a timeout of ``JSONLD_LOADER_TIMEOUT`` seconds. Repeated calls do
    nothing.
    """
    global _loader_installed
    if _loader_installed:
        return
    settings = get_settings()
    # PyLD (3.3) creates the requests session of its loader when the loader is
    # created. A cache installed globally afterwards (requests_cache
    # .install_cache) never reached that session, and every context was
    # fetched again for every document. The loader gets its cached session
    # explicitly instead.
    session = requests_cache.CachedSession(
        "jsonld_cache",
        backend="memory",
        expire_after=settings.JSONLD_CACHE_EXPIRE_AFTER,
    )
    session.hooks["response"].append(_raise_for_status)
    jsonld.set_document_loader(
        jsonld.requests_document_loader(
            timeout=settings.JSONLD_LOADER_TIMEOUT, session=session
        )
    )
    _loader_installed = True


def get_processor() -> jsonld.JsonLdProcessor:
    """The shared JSON-LD processor, with the cached loader installed.

    Returns:
        One :class:`pyld.jsonld.JsonLdProcessor` per process.
    """
    global _processor
    if _processor is None:
        install_document_loader()
        _processor = jsonld.JsonLdProcessor()
    return _processor
