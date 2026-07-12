"""Product reservations (layaway).

Creating a reservation HOLDS stock atomically (Product.reserved_quantity +=
qty, guarded by availability) without decrementing it. Completing releases the
hold and converts the lines into a Sale through finalize_sale — both folded
into ONE transaction (finalize_sale(commit=False)), so an over-sell or a
payment-rule violation rolls the whole thing back and the hold survives.
Cancelling (or expiry cleanup) simply releases the hold.

The deposit is recorded for reference; the payment at completion is collected
fresh at the caisse and is not auto-applied against the deposit.
"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from loguru import logger
from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import (
    AppError,
    InsufficientStockError,
    NotFoundError,
    ProductUnavailableError,
)
from app.models import Customer, Product, Reservation, ReservationItem
from app.models.reservation import ReservationStatus
from app.schemas.reservation import ReservationComplete, ReservationCreate
from app.schemas.sale import CartItem, CheckoutRequest
from app.services import pricing, sales


class ReservationNotActiveError(AppError):
    code = "reservation_not_active"

    def __init__(self) -> None:
        super().__init__("Cette réservation n'est plus active.")


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _hold_stock(
    db: Session, product_id: UUID, quantity: int, product_name: str
) -> None:
    """Atomically reserve `quantity` available units (no stock decrement)."""
    result = db.execute(
        update(Product)
        .where(
            Product.id == product_id,
            Product.deleted_at.is_(None),
            Product.stock_quantity - Product.reserved_quantity >= quantity,
        )
        .values(reserved_quantity=Product.reserved_quantity + quantity)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        raise InsufficientStockError(product_name=product_name, requested=quantity)


def _release_stock(db: Session, product_id: UUID, quantity: int) -> None:
    """Atomically release a previously held quantity (guarded ≥ 0)."""
    db.execute(
        update(Product)
        .where(
            Product.id == product_id,
            Product.reserved_quantity >= quantity,
        )
        .values(reserved_quantity=Product.reserved_quantity - quantity)
        .execution_options(synchronize_session=False)
    )


def create(db: Session, payload: ReservationCreate) -> dict:
    """Create a reservation, holding stock for every line atomically."""
    try:
        customer = db.scalar(
            select(Customer).where(
                Customer.id == payload.customer_id,
                Customer.store_id == payload.store_id,
                Customer.deleted_at.is_(None),
            )
        )
        if customer is None:
            raise NotFoundError("client", payload.customer_id)

        reservation = Reservation(
            store_id=payload.store_id,
            customer_id=payload.customer_id,
            expires_at=payload.expires_at,
            status=ReservationStatus.active,
            deposit_amount=payload.deposit_amount,
            notes=payload.notes or None,
        )
        db.add(reservation)

        for line in payload.items:
            product = db.scalar(
                select(Product).where(
                    Product.id == line.product_id,
                    Product.store_id == payload.store_id,
                    Product.deleted_at.is_(None),
                )
            )
            if product is None or not product.is_active:
                raise ProductUnavailableError(line.product_id)
            _hold_stock(db, product.id, line.quantity, product.name)
            unit_price = pricing.resolve_unit_price(
                product, line.price_level, line.quantity
            )
            db.add(
                ReservationItem(
                    store_id=payload.store_id,
                    reservation=reservation,
                    product_id=product.id,
                    quantity=line.quantity,
                    price_level=line.price_level,
                    unit_price_snapshot=unit_price,
                )
            )
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(reservation)
    logger.info("Reservation created | id={}", reservation.id)
    return _serialize(db, reservation.id)


def _load(db: Session, reservation_id: UUID) -> Reservation | None:
    return db.scalar(
        select(Reservation)
        .options(
            selectinload(Reservation.items).selectinload(ReservationItem.product),
        )
        .where(Reservation.id == reservation_id, Reservation.deleted_at.is_(None))
    )


def _serialize(db: Session, reservation_id: UUID) -> dict:
    reservation = _load(db, reservation_id)
    if reservation is None:
        raise NotFoundError("réservation", reservation_id)
    customer = db.scalar(select(Customer).where(Customer.id == reservation.customer_id))
    items = []
    total = Decimal("0.00")
    for item in reservation.items:
        if item.deleted_at is not None:
            continue
        line_total = (item.unit_price_snapshot * item.quantity).quantize(
            Decimal("0.01")
        )
        total += line_total
        items.append(
            {
                "id": item.id,
                "product_id": item.product_id,
                "product_name": item.product.name if item.product else "Produit",
                "quantity": item.quantity,
                "price_level": item.price_level,
                "unit_price_snapshot": item.unit_price_snapshot,
                "line_total": line_total,
            }
        )
    is_expired = (
        reservation.status == ReservationStatus.active
        and _naive(reservation.expires_at) < _now()
    )
    return {
        "id": reservation.id,
        "store_id": reservation.store_id,
        "customer_id": reservation.customer_id,
        "customer_name": customer.name if customer else None,
        "customer_phone": customer.phone if customer else None,
        "created_at": reservation.created_at,
        "expires_at": reservation.expires_at,
        "status": reservation.status,
        "deposit_amount": reservation.deposit_amount,
        "notes": reservation.notes,
        "sale_id": reservation.sale_id,
        "total_amount": total,
        "is_expired": is_expired,
        "items": items,
    }


def _naive(dt: datetime) -> datetime:
    return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt


def list_reservations(
    db: Session,
    store_id: UUID,
    status: str | None = None,
    customer_id: UUID | None = None,
) -> list[dict]:
    stmt = select(Reservation).where(
        Reservation.store_id == store_id, Reservation.deleted_at.is_(None)
    )
    if status is not None:
        stmt = stmt.where(Reservation.status == status)
    if customer_id is not None:
        stmt = stmt.where(Reservation.customer_id == customer_id)
    stmt = stmt.order_by(Reservation.created_at.desc())
    return [_serialize(db, r.id) for r in db.scalars(stmt)]


def get(db: Session, reservation_id: UUID) -> dict | None:
    reservation = _load(db, reservation_id)
    if reservation is None:
        return None
    return _serialize(db, reservation_id)


def complete(
    db: Session,
    reservation_id: UUID,
    payload: ReservationComplete,
    created_by_user_id: UUID | None = None,
) -> dict:
    """Release the hold and convert the reservation into a Sale, atomically."""
    try:
        reservation = _load(db, reservation_id)
        if reservation is None:
            raise NotFoundError("réservation", reservation_id)
        if reservation.status != ReservationStatus.active:
            raise ReservationNotActiveError()

        live_items = [i for i in reservation.items if i.deleted_at is None]
        for item in live_items:
            _release_stock(db, item.product_id, item.quantity)

        checkout = CheckoutRequest(
            store_id=reservation.store_id,
            items=[
                CartItem(
                    product_id=item.product_id,
                    quantity=item.quantity,
                    price_level=item.price_level,
                )
                for item in live_items
            ],
            payment=payload.payment,
        )
        sale = sales.finalize_sale(
            db, checkout, created_by_user_id=created_by_user_id, commit=False
        )
        reservation.status = ReservationStatus.completed
        reservation.sale_id = sale.id
        db.commit()
    except Exception:
        db.rollback()
        raise
    logger.info("Reservation completed | id={} sale_id={}", reservation_id, sale.id)
    return _serialize(db, reservation_id)


def cancel(db: Session, reservation_id: UUID) -> dict:
    """Cancel an active reservation and release its stock hold."""
    try:
        reservation = _load(db, reservation_id)
        if reservation is None:
            raise NotFoundError("réservation", reservation_id)
        if reservation.status != ReservationStatus.active:
            raise ReservationNotActiveError()
        for item in reservation.items:
            if item.deleted_at is None:
                _release_stock(db, item.product_id, item.quantity)
        reservation.status = ReservationStatus.cancelled
        db.commit()
    except Exception:
        db.rollback()
        raise
    logger.info("Reservation cancelled | id={}", reservation_id)
    return _serialize(db, reservation_id)
