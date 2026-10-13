from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base.

    SQLAlchemy >= 2.0 requires the class-based base. Older 1.x versions
    accepted (and ignored) declarative_base() kwargs, so subclassing
    DeclarativeBase keeps this project compatible with both.
    """

    pass
