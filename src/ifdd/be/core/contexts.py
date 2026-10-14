"""JSON-LD contexts: their kind, their name and who may use them.

Every stored row has exactly one ``@context`` URL. The last path segment of
that URL without ``.jsonld`` is the *context name*; the version in the path
does not count. There are three kinds of contexts:

=========  ===============================  =================================
kind       names                            access
=========  ===============================  =================================
base       ``base``                         node read / write role
aspect     the values of ``IFDD_ASPECTS``   node read / write role
domain     dotted names, ``a.b.example``    node role **and** a matching
                                            context pattern
=========  ===============================  =================================

Anything else is refused (HTTP 422), so a typo never makes a context public
by accident. Contexts are only accepted from below ``IFDD_SCHEMA_URL``.

A *context pattern* is a client role of the backend client whose name
contains a dot. A pattern matches the domain context of the same name and
every context below it, compared at label boundaries like DNS names:
``dom1.ifdd.de`` matches ``dom1.ifdd.de`` and ``sub1.dom1.ifdd.de``, but not
``xdom1.ifdd.de``. Read and write are not given per pattern: the node roles
(read, write) apply to every context a client may use.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping, Optional

from cachetools import TTLCache

from .cache_meta import CACHE_TERMS
from .config import get_settings

BASE_CONTEXT = "base"
CONTEXT_FILE_SUFFIX = ".jsonld"

_LABEL = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")


class ContextError(ValueError):
    """A context URL the backend does not accept (HTTP 422)."""


class ContextForbidden(PermissionError):
    """The client may not use this domain context (HTTP 403)."""


@dataclass(frozen=True)
class Context:
    """A context URL with its name; ``domain`` is True for a domain context."""

    url: str
    name: str
    domain: bool

    @property
    def domain_name(self) -> Optional[str]:
        """The name for a domain context, None for base and aspect contexts."""
        return self.name if self.domain else None


def generic_names() -> set[str]:
    """``base`` and the aspect names: the contexts every node reader may read."""
    return {BASE_CONTEXT, *get_settings().IFDD_ASPECTS.values()}


def parse(url: str) -> Context:
    """The context behind a URL, or :class:`ContextError`."""
    if not isinstance(url, str):
        raise ContextError("@context must be the URL of a context file")
    base = get_settings().IFDD_SCHEMA_URL.rstrip("/") + "/"
    if not url.startswith(base):
        raise ContextError(f"context {url!r} is not below {base}")
    file_name = url[len(base):].rsplit("/", 1)[-1]
    if not file_name.endswith(CONTEXT_FILE_SUFFIX):
        raise ContextError(f"context {url!r} does not name a {CONTEXT_FILE_SUFFIX} file")
    name = file_name[: -len(CONTEXT_FILE_SUFFIX)]
    if name in generic_names():
        return Context(url=url, name=name, domain=False)
    if is_domain_name(name):
        return Context(url=url, name=name, domain=True)
    raise ContextError(
        f"context name {name!r} is neither base, an aspect "
        f"({', '.join(sorted(generic_names() - {BASE_CONTEXT}))}) nor a domain "
        "name (lower-case labels a-z, 0-9 and '-', separated by dots)"
    )


def is_domain_name(name: str) -> bool:
    """At least two labels, each lower-case letters, digits and inner hyphens."""
    labels = name.split(".")
    return len(labels) >= 2 and all(_LABEL.match(label) for label in labels)


def matches(name: str, pattern: str) -> bool:
    """A pattern matches its own name and every name below it."""
    return name == pattern or name.endswith("." + pattern)


@dataclass(frozen=True)
class Access:
    """The context patterns of one client."""

    patterns: tuple[str, ...]

    @classmethod
    def from_token(cls, token_data: Mapping) -> "Access":
        """Patterns are the client roles of the backend client with a dot."""
        audience = get_settings().IFDD_OIDC_JWKS_AUDIENCE
        roles = token_data.get("resource_access", {}).get(audience, {}).get("roles", [])
        return cls(patterns=tuple(sorted({role.lower() for role in roles if "." in role})))

    def may_use(self, domain: Optional[str]) -> bool:
        """``domain`` is a domain context name, or None for base and aspects."""
        return domain is None or any(matches(domain, p) for p in self.patterns)

    def require(self, domain: Optional[str]) -> None:
        """Raise unless the client may use this context.

        Args:
            domain: A domain context name, or None for base and aspects.

        Raises:
            ContextForbidden: No pattern of the client matches ``domain``.
        """
        if not self.may_use(domain):
            raise ContextForbidden(f"no context pattern of this client matches {domain!r}")


# --- the namespace of a context ---------------------------------------------------


_namespaces: Optional[TTLCache] = None


def cache_namespace(context_url: str) -> str:
    """The namespace a context gives its c_* terms, e.g. ``https://type/v1/product/``.

    Kept per URL as long as the context itself (``JSONLD_CACHE_EXPIRE_AFTER``),
    so a read does not expand the terms again; failures are not kept.

    Found by expanding the six c_* terms with the context itself, so nothing
    is assumed about prefixes or the URL layout. Raises :class:`ContextError`
    if the context does not define all six terms in one namespace, or if that
    namespace does not end with ``/`` or ``#``: JSON-LD 1.1 uses a term as a
    prefix only then (section 4.1.5, compact IRIs).
    """
    global _namespaces
    if _namespaces is None:
        _namespaces = TTLCache(maxsize=1024, ttl=get_settings().JSONLD_CACHE_EXPIRE_AFTER)
    if context_url in _namespaces:
        return _namespaces[context_url]
    namespace = _find_namespace(context_url)
    _namespaces[context_url] = namespace
    return namespace


def _find_namespace(context_url: str) -> str:
    from .jsonld import get_processor

    probe = {"@context": context_url, **{term: "2000-01-01T00:00:00Z" for term in CACHE_TERMS}}
    expanded_list = get_processor().expand(probe, options=None)
    expanded = expanded_list[0] if expanded_list else {}
    namespaces: set[str] = set()
    for term in CACHE_TERMS:
        iri = next((key for key in expanded if key.endswith(term)), None)
        if iri is None:
            raise ContextError(f"context {context_url!r} does not define the term {term!r}")
        namespaces.add(iri[: -len(term)])
    if len(namespaces) != 1:
        raise ContextError(
            f"context {context_url!r} defines the c_* terms in more than one namespace: "
            + ", ".join(sorted(namespaces))
        )
    namespace = namespaces.pop()
    if not namespace.endswith(("/", "#")):
        raise ContextError(
            f"the namespace {namespace!r} of context {context_url!r} must end with '/' or '#'"
        )
    return namespace


def name_of(url: str) -> str:
    """The context name of a stored context URL, without checking it again."""
    file_name = url.rstrip("/").rsplit("/", 1)[-1]
    if file_name.endswith(CONTEXT_FILE_SUFFIX):
        return file_name[: -len(CONTEXT_FILE_SUFFIX)]
    return file_name
