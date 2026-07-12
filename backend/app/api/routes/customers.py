from uuid import UUID

from fastapi import APIRouter, Query

from app.api.deps import DbDep, ManagerDep
from app.core.exceptions import NotFoundError
from app.schemas.customer import CustomerCreate, CustomerRead, CustomerUpdate
from app.services import customers

router = APIRouter()


@router.get("", response_model=list[CustomerRead])
def list_customers(
    store_id: UUID,
    db: DbDep,
    q: str | None = Query(default=None, max_length=200),
    limit: int | None = Query(default=None, ge=1, le=200),
) -> list:
    """All customers of the store; q runs the smart search, limit caps results."""
    return customers.list_customers(db, store_id, query=q, limit=limit)


@router.get("/{customer_id}", response_model=CustomerRead)
def get_customer(customer_id: UUID, db: DbDep):
    customer = customers.get_customer(db, customer_id)
    if customer is None:
        raise NotFoundError("client", customer_id)
    return customer


@router.post("", response_model=CustomerRead, status_code=201)
def create_customer(payload: CustomerCreate, db: DbDep):
    return customers.create_customer(db, payload)


@router.patch("/{customer_id}", response_model=CustomerRead)
def update_customer(customer_id: UUID, payload: CustomerUpdate, db: DbDep):
    customer = customers.update_customer(db, customer_id, payload)
    if customer is None:
        raise NotFoundError("client", customer_id)
    return customer


@router.delete("/{customer_id}", status_code=204, dependencies=[ManagerDep])
def archive_customer(customer_id: UUID, db: DbDep) -> None:
    if customers.soft_delete_customer(db, customer_id) is None:
        raise NotFoundError("client", customer_id)
