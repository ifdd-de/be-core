"""The declarative base of the ORM models and its metadata."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base of all ORM models (SQLAlchemy 2.x typed mappings)."""


metadata = Base.metadata
