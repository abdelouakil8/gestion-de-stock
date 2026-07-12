from uuid import UUID

from fastapi import APIRouter

from app.api.deps import DbDep, ManagerDep
from app.core.exceptions import NotFoundError
from app.schemas.category import CategoryCreate, CategoryRead, CategoryUpdate
from app.services import categories

router = APIRouter()


@router.get("", response_model=list[CategoryRead])
def list_categories(store_id: UUID, db: DbDep) -> list:
    return categories.list_categories(db, store_id)


@router.post(
    "", response_model=CategoryRead, status_code=201, dependencies=[ManagerDep]
)
def create_category(payload: CategoryCreate, db: DbDep):
    return categories.create_category(db, payload)


@router.patch("/{category_id}", response_model=CategoryRead, dependencies=[ManagerDep])
def update_category(category_id: UUID, payload: CategoryUpdate, db: DbDep):
    category = categories.update_category(db, category_id, payload)
    if category is None:
        raise NotFoundError("catégorie", category_id)
    return category


@router.delete("/{category_id}", status_code=204, dependencies=[ManagerDep])
def archive_category(category_id: UUID, db: DbDep) -> None:
    if categories.soft_delete_category(db, category_id) is None:
        raise NotFoundError("catégorie", category_id)
