from uuid import UUID

from fastapi import APIRouter, Response

from app.api.deps import DbDep
from app.core.exceptions import NotFoundError
from app.schemas.sale import CheckoutRequest, PaymentCreate, SaleRead
from app.services import customers, payments, receipts, sales, stores
from app.services import settings as settings_service

router = APIRouter()


@router.post("/checkout", response_model=SaleRead, status_code=201)
def checkout(payload: CheckoutRequest, db: DbDep):
    """Finalize a cart. Price-level resolution, the price floor (prix super
    gros), the credit rules and the atomic stock decrement are all enforced
    server-side inside one transaction — nothing from the UI is trusted."""
    return sales.finalize_sale(db, payload)


@router.get("", response_model=list[SaleRead])
def list_sales(store_id: UUID, db: DbDep) -> list:
    return sales.list_sales(db, store_id)


@router.get("/{sale_id}", response_model=SaleRead)
def get_sale(sale_id: UUID, db: DbDep):
    sale = sales.get_sale(db, sale_id)
    if sale is None:
        raise NotFoundError("vente", sale_id)
    return sale


@router.post("/{sale_id}/payments", response_model=SaleRead, status_code=201)
def add_payment(sale_id: UUID, payload: PaymentCreate, db: DbDep):
    """Record a later payment on a sale with an outstanding balance.

    Overpayment is rejected; partial instalments and full settlement both
    work; the whole operation is atomic."""
    payments.record_payment(db, sale_id, payload.amount)
    return sales.get_sale(db, sale_id)


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
