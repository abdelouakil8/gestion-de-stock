"""User management — owner-only CRUD over the multi-role accounts."""

from uuid import UUID

from fastapi import APIRouter

from app.api.deps import DbDep, OwnerDep
from app.schemas.user import UserCreate, UserRead, UserUpdate
from app.services import users

router = APIRouter()


@router.get("", response_model=list[UserRead], dependencies=[OwnerDep])
def list_users(store_id: UUID, db: DbDep) -> list:
    """Every non-deleted user of the store (owner only)."""
    return users.list_users(db, store_id)


@router.post("", response_model=UserRead, status_code=201, dependencies=[OwnerDep])
def create_user(payload: UserCreate, db: DbDep):
    return users.create_user(db, payload)


@router.patch("/{user_id}", response_model=UserRead, dependencies=[OwnerDep])
def update_user(user_id: UUID, payload: UserUpdate, db: DbDep):
    """Update a user's name/role/PIN/active flag (owner only)."""
    return users.update_user(db, user_id, payload)


@router.delete("/{user_id}", status_code=204, dependencies=[OwnerDep])
def deactivate_user(user_id: UUID, db: DbDep) -> None:
    users.deactivate_user(db, user_id)
