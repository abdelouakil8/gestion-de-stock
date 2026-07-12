"""Daily cash-register closing (clôture de caisse).

day_summary() computes the automatic recap the operator reconciles against
(sales count, revenue, the payment-method split, discounts, refunds) for one
store-local calendar day. close_day() snapshots that recap together with the
physical cash counted and the computed gap into an immutable DayClosing row,
atomically and closable exactly once per day.

Timezone contract mirrors statistics.py: created_at is stored naive UTC, so a
store-local day is bounded with to_utc_naive() on the half-open interval
[start, next-day-start).
"""

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select, type_coerce
from sqlalchemy.orm import Session

from app.core.exceptions import DayAlreadyClosedError
from app.db.types import Money
from app.models import Payment, Refund, Sale, SaleItem
from app.models.day_closing import DayClosing
from app.schemas.day_closing import DayClosingCreate, DaySummary
from app.services.statistics import to_utc_naive

# Payment-method codes grouped into the drawer buckets shown on the closing.
_CARD_METHODS = {"card"}
_TRANSFER_METHODS = {"transfer", "virement"}
_CASH_METHODS = {"cash"}


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    """The store-local calendar day as a half-open naive-UTC [start, end)."""
    start_local = datetime.combine(day, time.min)
    end_local = start_local + timedelta(days=1)
    return to_utc_naive(start_local), to_utc_naive(end_local)


def _existing_closing(db: Session, store_id: UUID, day: date) -> DayClosing | None:
    return db.scalar(
        select(DayClosing).where(
            DayClosing.store_id == store_id,
            DayClosing.closing_date == day,
            DayClosing.deleted_at.is_(None),
        )
    )


def _compute_summary(db: Session, store_id: UUID, day: date) -> dict:
    """The raw figures for a day (Decimals), shared by the summary + closing."""
    start, end = _day_bounds(day)

    # Sales made that day: count + revenue + discounts (by Sale.created_at).
    sales_row = db.execute(
        select(
            func.count(func.distinct(Sale.id)).label("sales_count"),
            type_coerce(func.coalesce(func.sum(SaleItem.line_total), 0), Money()).label(
                "revenue"
            ),
            type_coerce(
                func.coalesce(func.sum(SaleItem.discount_amount), 0), Money()
            ).label("discounts"),
        )
        .join(SaleItem, SaleItem.sale_id == Sale.id)
        .where(
            Sale.store_id == store_id,
            Sale.deleted_at.is_(None),
            SaleItem.deleted_at.is_(None),
            Sale.created_at >= start,
            Sale.created_at < end,
        )
    ).one()

    # Cash flow IN: payments actually received that day, by method (a later
    # instalment on an old credit sale still enters today's drawer).
    method_rows = db.execute(
        select(
            Payment.payment_method,
            type_coerce(func.sum(Payment.amount), Money()).label("total"),
        )
        .join(Sale, Payment.sale_id == Sale.id)
        .where(
            Sale.store_id == store_id,
            Sale.deleted_at.is_(None),
            Payment.deleted_at.is_(None),
            Payment.created_at >= start,
            Payment.created_at < end,
        )
        .group_by(Payment.payment_method)
    ).all()

    cash = card = transfer = other = Decimal("0.00")
    for method, total in method_rows:
        total = total or Decimal("0.00")
        key = (method or "cash").lower()
        if key in _CASH_METHODS:
            cash += total
        elif key in _CARD_METHODS:
            card += total
        elif key in _TRANSFER_METHODS:
            transfer += total
        else:
            other += total

    # Cash flow OUT: refunds issued that day (assumed cash out of the drawer).
    refunds_total = db.scalar(
        select(
            type_coerce(func.coalesce(func.sum(Refund.total_amount), 0), Money())
        ).where(
            Refund.store_id == store_id,
            Refund.deleted_at.is_(None),
            Refund.created_at >= start,
            Refund.created_at < end,
        )
    ) or Decimal("0.00")

    expected_cash = cash - refunds_total

    return {
        "sales_count": int(sales_row.sales_count or 0),
        "total_revenue": sales_row.revenue or Decimal("0.00"),
        "cash_total": cash,
        "card_total": card,
        "transfer_total": transfer,
        "other_total": other,
        "total_discounts": sales_row.discounts or Decimal("0.00"),
        "total_refunds": refunds_total,
        "expected_cash": expected_cash,
    }


def day_summary(db: Session, store_id: UUID, day: date) -> DaySummary:
    """Section A recap + whether the day is already closed."""
    figures = _compute_summary(db, store_id, day)
    return DaySummary(
        date=day,
        already_closed=_existing_closing(db, store_id, day) is not None,
        **figures,
    )


def close_day(db: Session, data: DayClosingCreate) -> DayClosing:
    """Snapshot the day recap + physical count into an immutable closing.

    Rejected (409) if the day is already closed; otherwise persisted
    atomically. gap = physical_cash_count - expected_cash (signed)."""
    try:
        if _existing_closing(db, data.store_id, data.date) is not None:
            raise DayAlreadyClosedError(data.date)

        figures = _compute_summary(db, data.store_id, data.date)
        physical = Decimal(data.physical_cash_count)
        gap = physical - figures["expected_cash"]

        closing = DayClosing(
            store_id=data.store_id,
            closing_date=data.date,
            physical_cash_count=physical,
            gap=gap,
            notes=(data.notes or None),
            **figures,
        )
        db.add(closing)
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(closing)
    return closing
