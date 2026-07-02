import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, MetaData, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Named constraints from day one: required for clean ALTERs on SQLite
# (batch mode) and for a friction-free PostgreSQL migration later.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base for all ORM models — models stay dumb, no business logic."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class BaseModel(Base):
    """Columns every table must carry (project rule, non-negotiable):

    UUID primary key, created_at / updated_at, deleted_at (soft delete —
    financial records are never hard-deleted) and nullable is_synced /
    synced_at reserved for future cloud sync. Timestamps are UTC.
    """

    __abstract__ = True

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    is_synced: Mapped[bool | None] = mapped_column(default=None)
    synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )


class StoreScopedMixin:
    """store_id on every business table — multi-tenant ready from day one.

    No business logic may ever assume "there is only one store".
    """

    store_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("stores.id"), nullable=False, index=True
    )
