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
    SaleCustomerAlreadySetError,
    SaleHasCustomerError,
)
from app.models import Customer, Payment, Product, ProductPackaging, Sale, SaleItem
from app.schemas.sale import CheckoutRequest, PaymentInfo, SaleCreate
from app.services import inventory, invoicing, pricing


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

            # A priced packaging (carton) is an ADDITIONAL sale unit of the
            # same product: its own price triplet and floor, and one package
            # consumes packaging.unit_count base stock units. When no packaging
            # is chosen the base unit (unit_count=1, prices on Product) applies.
            packaging: ProductPackaging | None = None
            if line.packaging_id is not None:
                packaging = db.scalar(
                    select(ProductPackaging).where(
                        ProductPackaging.id == line.packaging_id,
                        ProductPackaging.product_id == product.id,
                        ProductPackaging.store_id == data.store_id,
                        ProductPackaging.deleted_at.is_(None),
                        ProductPackaging.is_active.is_(True),
                    )
                )
                if packaging is None:
                    raise NotFoundError("conditionnement", line.packaging_id)

            # The server resolves the price from the chosen named level (of the
            # packaging when set, else the product); a manual override is
            # allowed but faces the same floor (the packaging's super gros when
            # a packaging is sold). quantity is the number of packages; the
            # per-package price is what the customer is charged.
            if packaging is not None:
                unit_price = (
                    line.unit_price_override
                    if line.unit_price_override is not None
                    else pricing.resolve_packaging_price(packaging, line.price_level)
                )
                pricing.validate_price_floor(
                    product, unit_price, floor=packaging.price_super_gros
                )
                unit_count = packaging.unit_count
            else:
                unit_price = (
                    line.unit_price_override
                    if line.unit_price_override is not None
                    else pricing.resolve_unit_price(
                        product, line.price_level, line.quantity
                    )
                )
                pricing.validate_price_floor(product, unit_price)
                unit_count = 1

            # Stock is measured in BASE units: a line of `quantity` packages of
            # `unit_count` each takes quantity * unit_count off the shelf.
            base_units = line.quantity * unit_count
            inventory.decrement_stock(db, product, base_units)

            # Discount: validate that it doesn't push effective price below floor.
            discount = line.discount_amount or Decimal("0.00")
            if discount > 0:
                pkg_floor = packaging.price_super_gros if packaging else None
                pricing.validate_discount_floor(
                    product, unit_price, line.quantity, discount, floor=pkg_floor
                )

            # Revenue is per-package price × number of packages - discount.
            amount = pricing.line_total(unit_price, line.quantity, discount)
            total += amount
            sale_items.append(
                SaleItem(
                    store_id=data.store_id,
                    product_id=product.id,
                    quantity=line.quantity,
                    price_level=line.price_level,
                    packaging_id=packaging.id if packaging is not None else None,
                    packaging_label=packaging.label if packaging is not None else None,
                    unit_count=unit_count,
                    unit_price_applied=unit_price,
                    discount_amount=discount,
                    line_total=amount,
                )
            )

        paid_amount, customer_id = _resolve_checkout_payment(db, data, total)

        invoice_num = invoicing.allocate_invoice_number(db, data.store_id)
        sale = Sale(
            store_id=data.store_id,
            total_amount=total,
            paid_amount=paid_amount,
            customer_id=customer_id,
            invoice_number=invoice_num,
            items=sale_items,
        )
        db.add(sale)
        # Every payment — including the one at checkout — is a Payment row,
        # so paid_amount always equals SUM(payments) by construction.
        payment_method = data.payment.payment_method or "cash"
        if paid_amount > 0:
            db.add(
                Payment(
                    store_id=data.store_id,
                    sale=sale,
                    amount=paid_amount,
                    payment_method=payment_method,
                )
            )
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


def _attach_customer_fields(sale: Sale) -> Sale:
    """Mirror the attached customer's name/phone onto the Sale instance.

    These are read-only convenience fields injected onto the ORM object so
    SaleRead (from_attributes) can surface them without a separate query.
    None when the sale carries no customer (walk-in / anonymous).
    """
    customer = sale.customer
    sale.customer_name = customer.name if customer is not None else None
    sale.customer_phone = customer.phone if customer is not None else None
    return sale


def get_sale(db: Session, sale_id: UUID) -> Sale | None:
    sale = db.scalar(
        select(Sale)
        .options(
            selectinload(Sale.items),
            selectinload(Sale.payments),
            selectinload(Sale.customer),
        )
        .where(Sale.id == sale_id, Sale.deleted_at.is_(None))
    )
    if sale is not None:
        _attach_customer_fields(sale)
    return sale


def list_sales(
    db: Session,
    store_id: UUID,
    *,
    customer_id: UUID | None = None,
    guest: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[Sale]:
    """List a store's sales, newest first, with optional filters.

    guest: "pending" -> unresolved walk-in (no customer, not confirmed);
    "confirmed" -> intentionally anonymous (no customer, confirmed);
    "any" -> any sale without a customer.
    date_from/date_to bound created_at on the half-open interval [from, to).
    limit defaults to None (no LIMIT) for backward-compat with the existing
    no-arg call site; when passed it is clamped to [1, 500]. offset >= 0.
    """
    stmt = (
        select(Sale)
        .options(
            selectinload(Sale.items),
            selectinload(Sale.payments),
            selectinload(Sale.customer),
        )
        .where(Sale.store_id == store_id, Sale.deleted_at.is_(None))
        .order_by(Sale.created_at.desc())
    )

    if customer_id is not None:
        stmt = stmt.where(Sale.customer_id == customer_id)

    if guest == "pending":
        stmt = stmt.where(Sale.customer_id.is_(None), Sale.guest_confirmed_at.is_(None))
    elif guest == "confirmed":
        stmt = stmt.where(
            Sale.customer_id.is_(None), Sale.guest_confirmed_at.is_not(None)
        )
    elif guest == "any":
        stmt = stmt.where(Sale.customer_id.is_(None))

    if date_from is not None:
        stmt = stmt.where(Sale.created_at >= date_from)
    if date_to is not None:
        stmt = stmt.where(Sale.created_at < date_to)

    offset = max(0, offset)
    if limit is not None:
        stmt = stmt.limit(max(1, min(500, limit)))
    if offset:
        stmt = stmt.offset(offset)

    sales = list(db.scalars(stmt))
    for sale in sales:
        _attach_customer_fields(sale)
    return sales


def assign_customer(db: Session, sale_id: UUID, customer_id: UUID) -> Sale:
    """Attach a client to a sale that has none — the only path that ever sets
    customer_id after checkout. Assigning also cancels any anonymous mark."""
    sale = db.scalar(select(Sale).where(Sale.id == sale_id, Sale.deleted_at.is_(None)))
    if sale is None:
        raise NotFoundError("vente", sale_id)
    if sale.customer_id is not None:
        raise SaleCustomerAlreadySetError(sale_id)

    customer = db.scalar(
        select(Customer).where(
            Customer.id == customer_id,
            Customer.store_id == sale.store_id,
            Customer.deleted_at.is_(None),
        )
    )
    if customer is None:
        raise NotFoundError("client", customer_id)

    sale.customer_id = customer.id
    # Assigning a real customer supersedes any "leave anonymous" choice.
    sale.guest_confirmed_at = None
    db.commit()
    db.refresh(sale)
    sale.customer = customer
    return _attach_customer_fields(sale)


def confirm_guest(db: Session, sale_id: UUID) -> Sale:
    """Mark a walk-in (no-customer) sale as intentionally anonymous.

    Idempotent: if already confirmed the first timestamp is kept."""
    sale = db.scalar(
        select(Sale)
        .options(
            selectinload(Sale.items),
            selectinload(Sale.payments),
            selectinload(Sale.customer),
        )
        .where(Sale.id == sale_id, Sale.deleted_at.is_(None))
    )
    if sale is None:
        raise NotFoundError("vente", sale_id)
    if sale.customer_id is not None:
        raise SaleHasCustomerError(sale_id)

    if sale.guest_confirmed_at is None:
        sale.guest_confirmed_at = datetime.now(UTC)
        db.commit()
        db.refresh(sale)
    return _attach_customer_fields(sale)


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
