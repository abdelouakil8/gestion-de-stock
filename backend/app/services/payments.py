"""Payments on sales — append-only, auditable, overpayment always rejected.

Single source of truth: the payments table. sales.paid_amount is a cache of
SUM(payments.amount) maintained inside the same transaction as every
payment insert. The overpayment check is a single conditional UPDATE
(`SET paid_amount = paid_amount + :a WHERE paid_amount + :a <= total`), so
two near-simultaneous payments can never jointly exceed the total — the
loser's UPDATE matches zero rows and is rejected (same pattern as the
atomic stock decrement).
"""

from decimal import Decimal
from uuid import UUID

from loguru import logger
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.exceptions import (
    InvalidPaymentAmountError,
    NotFoundError,
    OverpaymentError,
)
from app.models import Payment, Sale


def record_payment(
    db: Session, sale_id: UUID, amount: Decimal, payment_method: str = "cash"
) -> Sale:
    """Add a payment to a sale with an outstanding balance, atomically.

    Works for a partial instalment or the full settlement; anything above
    the remaining balance is rejected (never clamped)."""
    if amount <= 0:
        raise InvalidPaymentAmountError(
            "Le montant du paiement doit être supérieur à zéro.",
            amount=str(amount),
        )

    try:
        sale = db.scalar(
            select(Sale).where(Sale.id == sale_id, Sale.deleted_at.is_(None))
        )
        if sale is None:
            raise NotFoundError("vente", sale_id)

        # Atomic guard: check and increment in ONE statement.
        result = db.execute(
            update(Sale)
            .where(
                Sale.id == sale.id,
                Sale.deleted_at.is_(None),
                Sale.paid_amount + amount <= Sale.total_amount,
            )
            .values(paid_amount=Sale.paid_amount + amount)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            raise OverpaymentError(
                balance=sale.total_amount - sale.paid_amount, attempted=amount
            )

        db.add(
            Payment(
                store_id=sale.store_id,
                sale_id=sale.id,
                amount=amount,
                payment_method=payment_method,
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(sale)
    logger.info(
        "Payment recorded | sale_id={} amount={} balance={}",
        sale.id,
        amount,
        sale.balance,
    )
    return sale


def list_payments(db: Session, sale_id: UUID) -> list[Payment]:
    return list(
        db.scalars(
            select(Payment)
            .where(Payment.sale_id == sale_id, Payment.deleted_at.is_(None))
            .order_by(Payment.created_at)
        )
    )
