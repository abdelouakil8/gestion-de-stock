"""Sales: checkout (the business transaction) and record CRUD.

finalize_sale() is the single entry point that turns a cart into a Sale:
server-side price-level resolution, the price floor (= prix super gros),
the credit rules and the atomic stock decrement all happen inside ONE
database transaction — on any failure nothing is committed. create_sale()
below it is Phase 1 dumb persistence, kept for seeding/tests; production
checkout must always go through finalize_sale().
"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import (
    CreditRequiresCustomerError,
    InvalidPaymentAmountError,
    NotFoundError,
    ProductUnavailableError,
)
from app.models import Customer, Payment, Product, Sale, SaleItem
from app.schemas.sale import CheckoutRequest, PaymentInfo, SaleCreate
from app.services import inventory, pricing


def _resolve_checkout_payment(
    db: Session, data: CheckoutRequest, total: Decimal
) -> tuple[Decimal, UUID | None]:
    """Apply the payment rules; returns (paid_amount, customer_id).

    RULE: a partial payment (credit sale) without an attached customer is
    always rejected — anonymous debt is unrecoverable.
    """
    info: PaymentInfo = data.payment

    if info.customer_id is not None:
        customer = db.scalar(
            select(Customer).where(
                Customer.id == info.customer_id,
                Customer.store_id == data.store_id,
                Customer.deleted_at.is_(None),
            )
        )
        if customer is None:
            raise NotFoundError("client", info.customer_id)

    if info.mode == "full":
        return total, info.customer_id

    # mode == "partial" — credit sale.
    if info.customer_id is None:
        raise CreditRequiresCustomerError()
    if info.amount_paid is None:
        raise InvalidPaymentAmountError(
            "Le montant payé est requis pour un paiement partiel."
        )
    if info.amount_paid < 0 or info.amount_paid >= total:
        raise InvalidPaymentAmountError(
            "Pour un paiement partiel, le montant payé doit être positif et "
            "strictement inférieur au total de la vente.",
            amount_paid=str(info.amount_paid),
            total=str(total),
        )
    return info.amount_paid, info.customer_id


def finalize_sale(db: Session, data: CheckoutRequest) -> Sale:
    """Validate and persist a cart as a Sale, atomically.

    Every rule is enforced here, server-side, at the moment of sale —
    regardless of what any UI claimed to have already checked.
    """
    try:
        sale_items: list[SaleItem] = []
        total = Decimal("0.00")

        for line in data.items:
            product = db.scalar(
                select(Product).where(
                    Product.id == line.product_id,
                    Product.store_id == data.store_id,
                    Product.deleted_at.is_(None),
                )
            )
            if product is None or not product.is_active:
                raise ProductUnavailableError(line.product_id)

            # The server resolves the price from the chosen named level;
            # a manual override is allowed but faces the same floor.
            unit_price = (
                line.unit_price_override
                if line.unit_price_override is not None
                else pricing.resolve_unit_price(
                    product, line.price_level, line.quantity
                )
            )
            pricing.validate_price_floor(product, unit_price)
            inventory.decrement_stock(db, product, line.quantity)

            amount = pricing.line_total(unit_price, line.quantity)
            total += amount
            sale_items.append(
                SaleItem(
                    store_id=data.store_id,
                    product_id=product.id,
                    quantity=line.quantity,
                    price_level=line.price_level,
                    unit_price_applied=unit_price,
                    line_total=amount,
                )
            )

        paid_amount, customer_id = _resolve_checkout_payment(db, data, total)

        sale = Sale(
            store_id=data.store_id,
            total_amount=total,
            paid_amount=paid_amount,
            customer_id=customer_id,
            items=sale_items,
        )
        db.add(sale)
        # Every payment — including the one at checkout — is a Payment row,
        # so paid_amount always equals SUM(payments) by construction.
        if paid_amount > 0:
            db.add(Payment(store_id=data.store_id, sale=sale, amount=paid_amount))
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(sale)
    logger.info(
        "Sale finalized | sale_id={} store_id={} total={} paid={} lines={}",
        sale.id,
        sale.store_id,
        sale.total_amount,
        sale.paid_amount,
        len(sale_items),
    )
    return sale


def create_sale(db: Session, data: SaleCreate) -> Sale:
    sale = Sale(
        store_id=data.store_id,
        total_amount=data.total_amount,
        paid_amount=data.total_amount,  # Phase 1 helper: fully paid
        items=[
            SaleItem(store_id=data.store_id, **item.model_dump()) for item in data.items
        ],
    )
    db.add(sale)
    db.commit()
    db.refresh(sale)
    return sale


def get_sale(db: Session, sale_id: UUID) -> Sale | None:
    return db.scalar(
        select(Sale)
        .options(selectinload(Sale.items), selectinload(Sale.payments))
        .where(Sale.id == sale_id, Sale.deleted_at.is_(None))
    )


def list_sales(db: Session, store_id: UUID) -> list[Sale]:
    return list(
        db.scalars(
            select(Sale)
            .options(selectinload(Sale.items), selectinload(Sale.payments))
            .where(Sale.store_id == store_id, Sale.deleted_at.is_(None))
            .order_by(Sale.created_at.desc())
        )
    )


def soft_delete_sale(db: Session, sale_id: UUID) -> Sale | None:
    """Soft-delete a sale and its items together (never hard-deleted)."""
    sale = get_sale(db, sale_id)
    if sale is not None:
        now = datetime.now(UTC)
        sale.deleted_at = now
        for item in sale.items:
            item.deleted_at = now
        db.commit()
        db.refresh(sale)
    return sale


def list_sale_items(db: Session, sale_id: UUID) -> list[SaleItem]:
    return list(
        db.scalars(
            select(SaleItem)
            .where(SaleItem.sale_id == sale_id, SaleItem.deleted_at.is_(None))
            .order_by(SaleItem.created_at)
        )
    )
