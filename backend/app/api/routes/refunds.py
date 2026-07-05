"""Refund (avoir) API routes — POST to create, GET to list."""

from uuid import UUID

from fastapi import APIRouter, Response

from app.api.deps import DbDep, OwnerPinDep
from app.core.exceptions import NotFoundError
from app.schemas.refund import RefundableItem, RefundCreate, RefundRead
from app.services import receipts, refunds, sales, stores
from app.services import settings as settings_service

router = APIRouter()


@router.post(
    "/{sale_id}/refund",
    response_model=RefundRead,
    status_code=201,
    dependencies=[OwnerPinDep],
)
def create_refund(sale_id: UUID, payload: RefundCreate, db: DbDep):
    """Create a refund (avoir) for items from a sale. PIN-gated."""
    refund = refunds.create_refund(
        db,
        sale_id=sale_id,
        items=[item.model_dump() for item in payload.items],
        reason=payload.reason,
    )
    return refund


@router.get("/{sale_id}/refunds", response_model=list[RefundRead])
def list_refunds(sale_id: UUID, db: DbDep):
    """All refunds issued against a sale, newest first."""
    return refunds.get_refunds_for_sale(db, sale_id)


@router.get("/{sale_id}/refundable", response_model=list[RefundableItem])
def get_refundable_items(sale_id: UUID, db: DbDep):
    """Remaining refundable quantities for each item on this sale."""
    return refunds.get_refundable_items(db, sale_id)


@router.get("/{sale_id}/refunds/{refund_id}/receipt")
def get_refund_receipt(sale_id: UUID, refund_id: UUID, db: DbDep) -> Response:
    """Printable avoir (refund) PDF."""
    sale = sales.get_sale(db, sale_id)
    if sale is None:
        raise NotFoundError("vente", sale_id)
    refund_list = refunds.get_refunds_for_sale(db, sale_id)
    refund = next((r for r in refund_list if r.id == refund_id), None)
    if refund is None:
        raise NotFoundError("avoir", refund_id)
    store = stores.get_store(db, sale.store_id)
    store_settings = settings_service.get_settings(db, sale.store_id)
    pdf = receipts.build_refund_receipt_pdf(refund, sale, store, store_settings)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="avoir_{refund_id}.pdf"'},
    )
