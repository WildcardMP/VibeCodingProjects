"""SQLAlchemy 2.0 Declarative Base.

`Base.metadata` is the target Alembic introspects in autogenerate mode. Every
ORM model in `app.models` must inherit from this Base so it lands in metadata.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Project-wide declarative base."""
