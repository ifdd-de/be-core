"""The ``nodes`` table: one row per version of a JSON-LD document.

A document is identified by its ``@id`` and the ``@context`` it was stored
with. Each row is one version of that pair and carries two periods (see
:mod:`ifdd.be.core.temporal`):

* ``valid_period`` -- valid time, from ``c_validNotBefore``/``c_validNotAfter``;
* ``sys_period`` -- system time, set by the backend; a row with an open-ended
  ``sys_period`` is *current*: it is what the backend knows now.

``domain`` holds the name of a domain context and is NULL for the base and
aspect contexts; reads filter on it (see :mod:`ifdd.be.core.contexts`).

The document itself (``json``, compacted, and ``expanded``) never contains the
c_* cache metadata; those values are the remaining columns.

Reads only ever look at current rows (:attr:`Node.is_current`), so every read
index is partial on that condition: retired versions do not make them larger.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    CheckConstraint,
    ColumnElement,
    Identity,
    Index,
    String,
    Text,
    cast,
    func,
    literal_column,
)
from sqlalchemy.dialects.postgresql import JSONB, TSTZRANGE, ExcludeConstraint, Range
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column

from .db.base import Base

# Extensions the table needs; created by ``ifdd-be-create-tables``.
#   btree_gist: "=" on text columns inside the GiST exclusion constraint
#   pg_trgm:    trigram index for the full-text search (``query=``)
REQUIRED_EXTENSIONS = ("btree_gist", "pg_trgm")


class Node(Base):
    """One version of one document (``@id``) in one context (``@context``).

    See the module docstring for the meaning of the columns; the table has no
    other users than :mod:`ifdd.be.core.repository` and the maintenance
    commands of :mod:`ifdd.be.core.tools.schema`.
    """

    __tablename__ = "nodes"

    row_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)

    # Identity of the document
    id: Mapped[str] = mapped_column(String)  # the @id
    id_path: Mapped[str] = mapped_column(String)  # path of the @id; how GET finds it
    context: Mapped[str] = mapped_column(String)  # the @context URL
    aspect: Mapped[str] = mapped_column(String)
    # Name of a domain context (``sub1.dom1.example``); NULL for the base and
    # aspect contexts, which every node reader may read (see contexts.py).
    domain: Mapped[Optional[str]] = mapped_column(String)

    # Bitemporal periods, half-open [lower, upper)
    sys_period: Mapped[Range[datetime]] = mapped_column(TSTZRANGE)
    valid_period: Mapped[Range[datetime]] = mapped_column(TSTZRANGE)

    # c_* cache metadata (see ifdd.be.core.cache_meta)
    src_created: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True))
    src_modified: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True))
    cache_created: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
    cache_updated: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))

    # The document, without c_* terms
    json: Mapped[dict] = mapped_column(JSONB)
    # Needed only to compare on write and to merge contexts on a single GET;
    # lists never load it. Queries that need it say so with undefer().
    expanded: Mapped[dict] = mapped_column(JSONB, deferred=True)

    @hybrid_property
    def is_current(self) -> bool:
        """The row is what the backend knows now (open-ended system time)."""
        return self.sys_period.upper is None

    @is_current.inplace.expression
    @classmethod
    def _is_current_expression(cls) -> ColumnElement[bool]:
        return func.upper_inf(cls.sys_period)

    __table_args__ = (
        # No two versions of one document overlap in both times at once.
        ExcludeConstraint(
            ("id", "="),
            ("context", "="),
            ("sys_period", "&&"),
            ("valid_period", "&&"),
            name="ex_nodes_one_version_at_a_time",
            using="gist",
        ),
        # Empty ranges never overlap anything and would slip past the
        # constraint; valid time always starts somewhere.
        CheckConstraint(
            "NOT isempty(sys_period) AND NOT isempty(valid_period) "
            "AND NOT lower_inf(sys_period) AND NOT lower_inf(valid_period)",
            name="ck_nodes_periods",
        ),
    )


# --- read indexes, all partial on current rows ----------------------------------
_current = func.upper_inf(Node.sys_period)

# Single document: GET /{segment}/{id}
Index("ix_nodes_current_id_path", Node.id_path, postgresql_where=_current)
# Graph traversal and id lists (@id)
Index("ix_nodes_current_id", Node.id, postgresql_where=_current)
# Lists of an aspect at an instant: context = ... AND valid_period @> at
Index(
    "ix_nodes_current_context_valid",
    Node.context,
    Node.valid_period,
    postgresql_using="gist",
    postgresql_where=_current,
)
# Filters on document fields (objType, objScope) as JSON containment, @>
Index(
    "ix_nodes_current_json",
    Node.json,
    postgresql_using="gin",
    postgresql_ops={"json": "jsonb_path_ops"},
    postgresql_where=_current,
)
# Full-text search: CAST(json AS TEXT) LIKE '%...%'
Index(
    "ix_nodes_current_json_trgm",
    cast(Node.json, Text).label("json_text"),
    postgresql_using="gin",
    postgresql_ops={"json_text": "gin_trgm_ops"},
    postgresql_where=_current,
)
# Sorting by the c_* columns
for _column in (Node.cache_updated, Node.cache_created, Node.src_created, Node.src_modified):
    Index(f"ix_nodes_current_{_column.key}", _column, postgresql_where=_current)


# Document fields lists may be sorted by; each has an expression index.
SORTABLE_FIELDS = ("objName", "objType", "objScope")


def document_field(name: str) -> ColumnElement[str]:
    """``json ->> 'name'`` with the name as an SQL literal.

    The default ``Node.json[name].astext`` sends the name as a bind
    parameter; an expression index only matches the literal form, so the
    index definitions and the ORDER BY both use this function.
    """
    if name not in SORTABLE_FIELDS:
        raise ValueError(f"{name!r} is not a sortable document field")
    return Node.json.op("->>")(literal_column(f"'{name}'"))


for _name in SORTABLE_FIELDS:
    Index(
        f"ix_nodes_current_{_name.lower()}",
        document_field(_name),
        postgresql_where=_current,
    )
