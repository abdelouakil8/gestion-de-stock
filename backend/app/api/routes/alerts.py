from uuid import UUID

from fastapi import APIRouter

from app.api.deps import DbDep
from app.schemas.alerts import AlertsResponse
from app.services import alerts

router = APIRouter()


@router.get("", response_model=AlertsResponse)
def get_alerts(store_id: UUID, db: DbDep):
    """Everything the notifications screen polls: low-stock products and
    outstanding credit sales (oldest debt first), with badge counters."""
    return alerts.get_alerts(db, store_id)
