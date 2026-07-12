from datetime import date, datetime
from uuid import UUID

from fastapi import APIRouter, Query, Response

from app.api.deps import CashierDep, CurrentUser, DbDep, ManagerDep
from app.core.exceptions import NotFoundError
from app.schemas.day_closing import DayClosingCreate, DayClosingRead, DaySummary
from app.schemas.sale import (
    AssignCustomerRequest,
    CheckoutRequest,
    OutstandingSale,
    PaymentCreate,
    SaleRead,
)
from app.services import (
    alerts,
    customers,
    day_closing,
    payments,
    receipts,
    reports,
    sales,
    stores,
)
from app.services import settings as settings_service

router = APIRouter()


@router.post("/checkout", response_model=SaleRead, status_code=201)
def checkout(payload: CheckoutRequest, db: DbDep, current: CurrentUser):
    """Finalize a cart. Price-level resolution, the price floor (prix super
    gros), the credit rules and the atomic stock decrement are all enforced
    server-side inside one transaction — nothing from the UI is trusted.

    Gated at the cashier floor; records which user rang the sale."""
    return sales.finalize_sale(db, payload, created_by_user_id=current.user_id)


@router.get("", response_model=list[SaleRead])
def list_sales(
    db: DbDep,
    store_id: UUID,
    customer_id: UUID | None = None,
    created_by_user_id: UUID | None = None,
    guest: str | None = Query(default=None, pattern="^(pending|confirmed|any)$"),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int | None = Query(default=None, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list:
    return sales.list_sales(
        db,
        store_id,
        customer_id=customer_id,
        created_by_user_id=created_by_user_id,
        guest=guest,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )


# ---- literal paths, registered BEFORE "/{sale_id}" so they win the match ----


@router.get(
    "/outstanding",
    response_model=list[OutstandingSale],
    dependencies=[ManagerDep],
)
def list_outstanding(store_id: UUID, db: DbDep) -> list:
    """Every credit sale with money still owed, oldest debt first (owner)."""
    return alerts.outstanding_credits(db, store_id)


@router.get("/outstanding.pdf", dependencies=[ManagerDep])
def outstanding_report(store_id: UUID, db: DbDep) -> Response:
    """A4 PDF summary of every outstanding customer debt (Créances export)."""
    store_settings = settings_service.get_settings(db, store_id)
    language = getattr(store_settings, "ui_language", "fr") if store_settings else "fr"
    pdf = reports.build_debt_report_pdf(db, store_id, language=language)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="creances.pdf"'},
    )


@router.get("/day-summary", response_model=DaySummary, dependencies=[ManagerDep])
def day_summary(store_id: UUID, day: date, db: DbDep) -> DaySummary:
    """Section-A recap for one store-local calendar day + already-closed flag."""
    return day_closing.day_summary(db, store_id, day)


@router.post(
    "/close-day",
    response_model=DayClosingRead,
    status_code=201,
    dependencies=[ManagerDep],
)
def close_day(payload: DayClosingCreate, db: DbDep) -> DayClosingRead:
    """Persist the day closing (rejected if the day is already closed)."""
    return day_closing.close_day(db, payload)


@router.get("/close-day.pdf", dependencies=[ManagerDep])
def closing_report(
    store_id: UUID,
    day: date,
    db: DbDep,
    physical_cash_count: str = Query(default="0"),
    notes: str | None = None,
) -> Response:
    """Printable clôture PDF for the given day + physical count (owner)."""
    from decimal import Decimal, InvalidOperation

    try:
        physical = Decimal(physical_cash_count).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        physical = Decimal("0.00")
    summary = day_closing.day_summary(db, store_id, day)
    gap = physical - summary.expected_cash
    store = stores.get_store(db, store_id)
    store_settings = settings_service.get_settings(db, store_id)
    pdf = receipts.build_closing_pdf(
        summary, physical, gap, store, store_settings, day, notes
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="cloture_{day}.pdf"'},
    )


@router.get("/{sale_id}", response_model=SaleRead)
def get_sale(sale_id: UUID, db: DbDep):
    sale = sales.get_sale(db, sale_id)
    if sale is None:
        raise NotFoundError("vente", sale_id)
    return sale


@router.post(
    "/{sale_id}/payments",
    response_model=SaleRead,
    status_code=201,
    dependencies=[CashierDep],
)
def add_payment(sale_id: UUID, payload: PaymentCreate, db: DbDep):
    """Record a later payment on a sale with an outstanding balance.

    Overpayment is rejected; partial instalments and full settlement both
    work; the whole operation is atomic."""
    payments.record_payment(db, sale_id, payload.amount, payload.payment_method)
    return sales.get_sale(db, sale_id)


@router.post("/{sale_id}/customer", response_model=SaleRead)
def assign_customer(sale_id: UUID, payload: AssignCustomerRequest, db: DbDep):
    """Attach a client to a sale that has none. Rejected (409) if the sale
    already carries a customer; assigning cancels any anonymous mark."""
    return sales.assign_customer(db, sale_id, payload.customer_id)


@router.post("/{sale_id}/confirm-guest", response_model=SaleRead)
def confirm_guest(sale_id: UUID, db: DbDep):
    """Mark a walk-in sale as intentionally anonymous. Idempotent; rejected
    (409) if the sale already has a customer."""
    return sales.confirm_guest(db, sale_id)


@router.get("/{sale_id}/receipt")
def get_receipt(sale_id: UUID, db: DbDep) -> Response:
    """Printable PDF receipt for a finalized sale."""
    sale = sales.get_sale(db, sale_id)
    if sale is None:
        raise NotFoundError("vente", sale_id)
    store = stores.get_store(db, sale.store_id)
    store_settings = settings_service.get_settings(db, sale.store_id)
    customer = (
        customers.get_customer(db, sale.customer_id)
        if sale.customer_id is not None
        else None
    )
    pdf = receipts.build_receipt_pdf(sale, store, store_settings, customer)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="recu_{sale_id}.pdf"'},
    )
