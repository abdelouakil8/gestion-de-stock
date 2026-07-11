"""Purchasing — receive stock from suppliers, atomically.

Same commit-or-rollback discipline as finalize_sale: if ANY line fails
(product not found, etc.) nothing is persisted.
"""

import uuid as _uuid
from decimal import Decimal
from uuid import UUID

from loguru import logger
from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import (
    InvalidPaymentAmountError,
    NotFoundError,
    OverpaymentError,
)
from app.models import Product
from app.models.purchase_order import (
    PurchaseOrder,
    PurchaseOrderItem,
    SupplierPayment,
)
from app.models.stock_movement import MovementType
from app.models.supplier import Supplier
from app.schemas.supplier import PurchaseOrderCreate
from app.services import inventory


def receive_stock(db: Session, data: PurchaseOrderCreate) -> PurchaseOrder:
    """Create a purchase order and atomically increment stock for each line."""
    try:
        order_id = _uuid.uuid4()
        supplier = db.scalar(
            select(Supplier).where(
                Supplier.id == data.supplier_id,
                Supplier.store_id == data.store_id,
                Supplier.deleted_at.is_(None),
            )
        )
        if supplier is None:
            raise NotFoundError("fournisseur", data.supplier_id)

        items: list[PurchaseOrderItem] = []
        total = Decimal("0.00")

        for line in data.items:
            product = db.scalar(
                select(Product).where(
                    Product.id == line.product_id,
                    Product.store_id == data.store_id,
                    Product.deleted_at.is_(None),
                )
            )
            if product is None:
                raise NotFoundError("produit", line.product_id)

            line_total = (line.unit_cost * line.quantity).quantize(Decimal("0.01"))
            total += line_total

            inventory.increment_stock(
                db,
                product.id,
                line.quantity,
                ref_id=order_id,
                movement_type=MovementType.purchase,
            )

            items.append(
                PurchaseOrderItem(
                    store_id=data.store_id,
                    product_id=product.id,
                    quantity=line.quantity,
                    unit_cost=line.unit_cost,
                    line_total=line_total,
                )
            )

        paid = Decimal("0.00")
        if data.payment_amount and data.payment_amount > 0:
            if data.payment_amount > total:
                raise InvalidPaymentAmountError(
                    "Le paiement dépasse le total de la commande.",
                    amount_paid=str(data.payment_amount),
                    total=str(total),
                )
            paid = data.payment_amount

        order = PurchaseOrder(
            id=order_id,
            store_id=data.store_id,
            supplier_id=data.supplier_id,
            total_amount=total,
            paid_amount=paid,
            items=items,
        )
        db.add(order)

        if paid > 0:
            db.add(
                SupplierPayment(
                    store_id=data.store_id,
                    order=order,
                    amount=paid,
                    payment_method=data.payment_method,
                )
            )
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(order)
    logger.info(
        "Stock received | order_id={} supplier_id={} total={} lines={}",
        order.id,
        order.supplier_id,
        order.total_amount,
        len(items),
    )
    return order


def record_supplier_payment(
    db: Session, order_id: UUID, amount: Decimal, payment_method: str = "cash"
) -> PurchaseOrder:
    """Add a payment to a purchase order — same atomic pattern as sales."""
    if amount <= 0:
        raise InvalidPaymentAmountError(
            "Le montant doit être supérieur à zéro.", amount=str(amount)
        )

    try:
        order = db.scalar(
            select(PurchaseOrder).where(
                PurchaseOrder.id == order_id,
                PurchaseOrder.deleted_at.is_(None),
            )
        )
        if order is None:
            raise NotFoundError("commande", order_id)

        result = db.execute(
            update(PurchaseOrder)
            .where(
                PurchaseOrder.id == order.id,
                PurchaseOrder.deleted_at.is_(None),
                PurchaseOrder.paid_amount + amount <= PurchaseOrder.total_amount,
            )
            .values(paid_amount=PurchaseOrder.paid_amount + amount)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            raise OverpaymentError(
                balance=order.total_amount - order.paid_amount,
                attempted=amount,
            )

        db.add(
            SupplierPayment(
                store_id=order.store_id,
                order_id=order.id,
                amount=amount,
                payment_method=payment_method,
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(order)
    return order


def get_order(db: Session, order_id: UUID) -> PurchaseOrder | None:
    return db.scalar(
        select(PurchaseOrder)
        .options(
            selectinload(PurchaseOrder.items),
            selectinload(PurchaseOrder.payments),
            selectinload(PurchaseOrder.supplier),
        )
        .where(PurchaseOrder.id == order_id, PurchaseOrder.deleted_at.is_(None))
    )


def list_orders(
    db: Session, store_id: UUID, supplier_id: UUID | None = None
) -> list[PurchaseOrder]:
    stmt = (
        select(PurchaseOrder)
        .options(selectinload(PurchaseOrder.items))
        .where(
            PurchaseOrder.store_id == store_id,
            PurchaseOrder.deleted_at.is_(None),
        )
        .order_by(PurchaseOrder.created_at.desc())
    )
    if supplier_id is not None:
        stmt = stmt.where(PurchaseOrder.supplier_id == supplier_id)
    return list(db.scalars(stmt))
