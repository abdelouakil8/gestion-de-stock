from uuid import UUID

from fastapi import APIRouter

from app.api.deps import DbDep, OwnerPinDep
from app.schemas.settings import SettingsRead, SettingsUpdate
from app.services import settings as settings_service

router = APIRouter()


@router.get("", response_model=SettingsRead)
def get_settings(store_id: UUID, db: DbDep):
    """Store settings (created with defaults on first access)."""
    return settings_service.get_settings(db, store_id)


@router.put("", response_model=SettingsRead, dependencies=[OwnerPinDep])
def update_settings(store_id: UUID, payload: SettingsUpdate, db: DbDep):
    return settings_service.update_settings(db, store_id, payload)
