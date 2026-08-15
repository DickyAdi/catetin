"""Shared declarative base and naming convention for all persistence rows."""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """All persistence tables. No domain logic here."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


# Server-generated columns (created_at, updated_at, received_at) are fetched
# back via RETURNING on insert so repositories can hand back a fully
# populated domain object without a second round trip.
EAGER_DEFAULTS = {"eager_defaults": True}
