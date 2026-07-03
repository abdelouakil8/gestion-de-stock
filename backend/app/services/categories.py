"""CRUD for categories. No business logic — Phase 2 owns the rules."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Category
from app.schemas.category import CategoryCreate, CategoryUpdate


def create_category(db: Session, data: CategoryCreate) -> Category:
    category = Category(**data.model_dump())
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


def get_category(db: Session, category_id: UUID) -> Category | None:
    return db.scalar(
        select(Category).where(
            Category.id == category_id, Category.deleted_at.is_(None)
        )
    )


def list_categories(db: Session, store_id: UUID) -> list[Category]:
    return list(
        db.scalars(
            select(Category)
            .where(Category.store_id == store_id, Category.deleted_at.is_(None))
            .order_by(Category.name)
        )
    )


def update_category(
    db: Session, category_id: UUID, data: CategoryUpdate
) -> Category | None:
    category = get_category(db, category_id)
    if category is not None:
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(category, field, value)
        db.commit()
        db.refresh(category)
    return category


def soft_delete_category(db: Session, category_id: UUID) -> Category | None:
    category = get_category(db, category_id)
    if category is not None:
        category.deleted_at = datetime.now(UTC)
        db.commit()
        db.refresh(category)
    return category
