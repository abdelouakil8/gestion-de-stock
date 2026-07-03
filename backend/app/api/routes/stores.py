from fastapi import APIRouter

from app.api.deps import DbDep
from app.schemas.store import StoreCreate, StoreRead
from app.services import stores

router = APIRouter()


@router.get("", response_model=list[StoreRead])
def list_stores(db: DbDep) -> list:
    return stores.list_stores(db)


@router.post("", response_model=StoreRead, status_code=201)
def create_store(payload: StoreCreate, db: DbDep):
    return stores.create_store(db, payload)
