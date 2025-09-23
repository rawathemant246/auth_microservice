from sqlalchemy.orm import DeclarativeBase

from auth_microservice.db.meta import meta


class Base(DeclarativeBase):
    """Base for all models."""

    metadata = meta
