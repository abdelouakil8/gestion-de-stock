"""Refund (avoir) service — atomic partial/full returns with stock restoration.

Core invariants:
- Cumulative refunded quantity per sale_item never exceeds the original qty.
- Total refund amount across all refunds on a sale never exceeds paid_amount.
- Stock is restored atomically: quantity × unit_count base units per item.
- Refund rows are IMMUTABLE — never updated or deleted after creation.
"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import (
    NotFoundError,
    RefundExceedsPaidAmountError,
    RefundExceedsQuantityError,
)
from app.models.refund import Refund, RefundItem
from app.models.sale import Sale, SaleItem
from app.models.stock_movement import MovementType
from app.services.inventory import increment_stock


def _already_refunded_qty(db: Session, sale_item_id: UUID) -> int:
    """Sum of quantities already refunded for a specific sale item."""
    result = db.execute(
        select(func.coalesce(func.sum(RefundItem.quantity), 0)).where(
            RefundItem.sale_item_id == sale_item_id
        )
    )
    return int(result.scalar())


def _total_refunded_amount(db: Session, sale_id: UUID) -> Decimal:
    """Sum of all refund totals already issued against this sale."""
    result = db.execute(
        select(func.coalesce(func.sum(Refund.total_amount), 0)).where(
            Refund.sale_id == sale_id
        )
    )
    return Decimal(str(result.scalar()))


def create_refund(
    db: Session,
    sale_id: UUID,
    items: list[dict],
    reason: str | None = None,
) -> Refund:
    """Create a refund atomically: validate, restore stock, persist.

    items: [{sale_item_id: UUID, quantity: int}]
    Each item refunds `quantity` packages (or units if no packaging) at the
    original sale price. Stock is restored by quantity × unit_count.

    Raises on invalid sale, over-refund by quantity, or over-refund by amount.
    """
    sale = db.get(Sale, sale_id)
    if sale is None or sale.deleted_at is not None:
        raise NotFoundError("vente", sale_id)

    sale_items_map: dict[UUID, SaleItem] = {si.id: si for si in sale.items}
    refund_items: list[RefundItem] = []
    refund_total = Decimal("0.00")

    for item_req in items:
        si_id = UUID(str(item_req["sale_item_id"]))
        qty = int(item_req["quantity"])

        sale_item = sale_items_map.get(si_id)
        if sale_item is None:
            raise NotFoundError("ligne de vente", si_id)

        already = _already_refunded_qty(db, si_id)
        available = sale_item.quantity - already
        if qty > available:
            product = sale_item.product
            raise RefundExceedsQuantityError(
                product.name if product else "?", available, qty
            )

        line_total = sale_item.unit_price_applied * qty
        refund_total += line_total

        refund_items.append(
            RefundItem(
                store_id=sale.store_id,
                sale_item_id=si_id,
                quantity=qty,
                unit_count=sale_item.unit_count,
                unit_price_refunded=sale_item.unit_price_applied,
                line_total=line_total,
            )
        )

    # Cap: total refunded across ALL refunds on this sale must not exceed paid.
    previous_refunded = _total_refunded_amount(db, sale_id)
    cumulative = previous_refunded + refund_total
    if cumulative > sale.paid_amount:
        raise RefundExceedsPaidAmountError(sale.paid_amount, cumulative)

    # Persist refund.
    refund = Refund(
        store_id=sale.store_id,
        sale_id=sale_id,
        reason=reason,
        total_amount=refund_total,
    )
    db.add(refund)
    db.flush()

    for ri in refund_items:
        ri.refund_id = refund.id
        db.add(ri)

    # Restore stock atomically.
    for ri in refund_items:
        sale_item = sale_items_map[ri.sale_item_id]
        base_units = ri.quantity * ri.unit_count
        increment_stock(
            db,
            sale_item.product_id,
            base_units,
            ref_id=refund.id,
            movement_type=MovementType.refund,
        )

    db.commit()
    db.refresh(refund)
    return refund


def get_refunds_for_sale(db: Session, sale_id: UUID) -> list[Refund]:
    """All refunds issued against a sale, newest first."""
    result = db.execute(
        select(Refund)
        .where(Refund.sale_id == sale_id)
        .order_by(Refund.created_at.desc())
    )
    return list(result.scalars().all())


def get_refundable_items(db: Session, sale_id: UUID) -> list[dict]:
    """For each sale item, compute how many units remain refundable."""
    sale = db.get(Sale, sale_id)
    if sale is None or sale.deleted_at is not None:
        raise NotFoundError("vente", sale_id)

    result = []
    for si in sale.items:
        already = _already_refunded_qty(db, si.id)
        available = si.quantity - already
        if available > 0:
            result.append(
                {
                    "sale_item_id": str(si.id),
                    "product_id": str(si.product_id),
                    "product_name": si.product.name if si.product else "?",
                    "packaging_label": si.packaging_label,
                    "unit_count": si.unit_count,
                    "original_quantity": si.quantity,
                    "already_refunded": already,
                    "available": available,
                    "unit_price": str(si.unit_price_applied),
                }
            )
    return result
