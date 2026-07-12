"""Product reservations (layaway) — manager+ operations."""

from uuid import UUID

from fastapi import APIRouter, Query

from app.api.deps import CurrentManager, DbDep, ManagerDep
from app.core.exceptions import NotFoundError
from app.schemas.reservation import (
    ReservationComplete,
    ReservationCreate,
    ReservationRead,
)
from app.services import reservations

router = APIRouter()


@router.post(
    "", response_model=ReservationRead, status_code=201, dependencies=[ManagerDep]
)
def create_reservation(payload: ReservationCreate, db: DbDep):
    """Create a reservation, holding stock for every line."""
    return reservations.create(db, payload)


@router.get("", response_model=list[ReservationRead], dependencies=[ManagerDep])
def list_reservations(
    store_id: UUID,
    db: DbDep,
    status: str | None = Query(default=None, pattern="^(active|completed|cancelled)$"),
    customer_id: UUID | None = None,
) -> list:
    return reservations.list_reservations(
        db, store_id, status=status, customer_id=customer_id
    )


@router.get(
    "/{reservation_id}", response_model=ReservationRead, dependencies=[ManagerDep]
)
def get_reservation(reservation_id: UUID, db: DbDep):
    reservation = reservations.get(db, reservation_id)
    if reservation is None:
        raise NotFoundError("réservation", reservation_id)
    return reservation


@router.post("/{reservation_id}/complete", response_model=ReservationRead)
def complete_reservation(
    reservation_id: UUID,
    payload: ReservationComplete,
    db: DbDep,
    current: CurrentManager,
):
    """Convert the reservation into a Sale (releases the hold), paying via the
    provided payment info."""
    return reservations.complete(
        db, reservation_id, payload, created_by_user_id=current.user_id
    )


@router.post(
    "/{reservation_id}/cancel",
    response_model=ReservationRead,
    dependencies=[ManagerDep],
)
def cancel_reservation(reservation_id: UUID, db: DbDep):
    """Cancel an active reservation and restore its held stock."""
    return reservations.cancel(db, reservation_id)
