from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import DbDep, OwnerPinDep
from app.services import admin

router = APIRouter()


class FactoryResetResult(BaseModel):
    deleted: dict[str, int]


@router.post(
    "/factory-reset", response_model=FactoryResetResult, dependencies=[OwnerPinDep]
)
def factory_reset(db: DbDep):
    """Erase ALL business data and media. Owner PIN required; the client
    asks the user to TYPE the PIN again — the cached one is never reused
    for this action."""
    return FactoryResetResult(deleted=admin.factory_reset(db))
