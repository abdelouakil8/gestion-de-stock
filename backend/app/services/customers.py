"""Customers: CRUD, search, and per-customer analytics (Phase 6).

Phone numbers are unique per store among non-deleted customers — enforced
here (French error) and backstopped by a partial unique index.
All monetary aggregation stays on the Money column type (BIGINT minor
units), so SQL SUMs are exact integer arithmetic — no float drift.
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import desc, func, select, type_coerce
from sqlalchemy.orm import Session

from app.core.exceptions import CustomerPhoneExistsError
from app.core.textnorm import normalize_text
from app.db.types import Money
from app.models import Customer, Product, Sale, SaleItem
from app.schemas.customer import CustomerCreate, CustomerUpdate
from app.schemas.statistics import CustomerStats, TopCustomer
from app.services import search


def _customer_search_text(name: str, phone: str, note: str | None) -> str:
    """Canonical search string — mirrored in the migration backfill."""
    return normalize_text(f"{name} {phone} {note or ''}")


def _phone_taken(
    db: Session, store_id: UUID, phone: str, exclude_id: UUID | None = None
) -> bool:
    query = select(Customer.id).where(
        Customer.store_id == store_id,
        Customer.phone == phone,
        Customer.deleted_at.is_(None),
    )
    if exclude_id is not None:
        query = query.where(Customer.id != exclude_id)
    return db.scalar(query) is not None


def create_customer(db: Session, data: CustomerCreate) -> Customer:
    if _phone_taken(db, data.store_id, data.phone):
        raise CustomerPhoneExistsError(data.phone)
    customer = Customer(**data.model_dump())
    customer.search_text = _customer_search_text(
        customer.name, customer.phone, customer.note
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


def get_customer(db: Session, customer_id: UUID) -> Customer | None:
    return db.scalar(
        select(Customer).where(
            Customer.id == customer_id, Customer.deleted_at.is_(None)
        )
    )


def list_customers(
    db: Session,
    store_id: UUID,
    *,
    query: str | None = None,
    limit: int | None = None,
) -> list[Customer]:
    """All customers of a store, optionally filtered by name, phone or note.

    With no query this returns every non-deleted customer of the store ordered
    by name (no limit). A query delegates to the smart search engine (LIKE
    prefilter + fuzzy fallback), which owns the matching logic.
    """
    if query is None and limit is None:
        return list(
            db.scalars(
                select(Customer)
                .where(Customer.store_id == store_id, Customer.deleted_at.is_(None))
                .order_by(Customer.name)
            )
        )
    return search.search_customers(
        db, store_id=store_id, query=query, limit=(limit or 20)
    )


def update_customer(
    db: Session, customer_id: UUID, data: CustomerUpdate
) -> Customer | None:
    customer = get_customer(db, customer_id)
    if customer is not None:
        changes = data.model_dump(exclude_unset=True)
        new_phone = changes.get("phone")
        if new_phone is not None and _phone_taken(
            db, customer.store_id, new_phone, exclude_id=customer.id
        ):
            raise CustomerPhoneExistsError(new_phone)
        for field, value in changes.items():
            setattr(customer, field, value)
        # Recompute after all fields are merged so name/phone/note changes in
        # the same PATCH produce a single canonical string.
        customer.search_text = _customer_search_text(
            customer.name, customer.phone, customer.note
        )
        db.commit()
        db.refresh(customer)
    return customer


def soft_delete_customer(db: Session, customer_id: UUID) -> Customer | None:
    """Archive a customer. Sale history keeps referencing the row."""
    customer = get_customer(db, customer_id)
    if customer is not None:
        customer.deleted_at = datetime.now(UTC)
        db.commit()
        db.refresh(customer)
    return customer


# ------------------------------------------------------------- analytics


def customer_stats(db: Session, customer_id: UUID) -> CustomerStats | None:
    """Lifetime figures for one customer (owner view — includes profit)."""
    customer = get_customer(db, customer_id)
    if customer is None:
        return None

    sale_row = db.execute(
        select(
            type_coerce(func.coalesce(func.sum(Sale.total_amount), 0), Money()).label(
                "revenue"
            ),
            type_coerce(
                func.coalesce(func.sum(Sale.total_amount - Sale.paid_amount), 0),
                Money(),
            ).label("outstanding"),
            func.count(Sale.id).label("sales_count"),
            func.max(Sale.created_at).label("last_purchase_at"),
        ).where(Sale.customer_id == customer.id, Sale.deleted_at.is_(None))
    ).one()

    profit = db.scalar(
        select(
            type_coerce(
                func.coalesce(
                    func.sum(
                        SaleItem.line_total
                        - Product.cost_price
                        * SaleItem.quantity
                        * SaleItem.unit_count
                    ),
                    0,
                ),
                Money(),
            )
        )
        .select_from(SaleItem)
        .join(Sale, SaleItem.sale_id == Sale.id)
        .join(Product, SaleItem.product_id == Product.id)
        .where(
            Sale.customer_id == customer.id,
            Sale.deleted_at.is_(None),
            SaleItem.deleted_at.is_(None),
        )
    )

    return CustomerStats(
        customer_id=customer.id,
        name=customer.name,
        phone=customer.phone,
        total_revenue=sale_row.revenue,
        total_profit=profit,
        sales_count=sale_row.sales_count,
        outstanding_balance=sale_row.outstanding,
        last_purchase_at=sale_row.last_purchase_at,
    )


def top_customers(
    db: Session,
    store_id: UUID,
    date_from: datetime,
    date_to: datetime,
    limit: int = 10,
) -> list[TopCustomer]:
    """Customers ranked by revenue over a date range (inclusive bounds)."""
    rows = db.execute(
        select(
            Customer.id.label("customer_id"),
            Customer.name.label("name"),
            Customer.phone.label("phone"),
            type_coerce(func.sum(Sale.total_amount), Money()).label("revenue"),
            func.count(Sale.id).label("sales_count"),
        )
        .join(Sale, Sale.customer_id == Customer.id)
        .where(
            Sale.store_id == store_id,
            Sale.deleted_at.is_(None),
            Sale.created_at >= date_from,
            Sale.created_at <= date_to,
        )
        .group_by(Customer.id, Customer.name, Customer.phone)
        .order_by(desc("revenue"), Customer.name)
        .limit(limit)
    ).all()
    return [TopCustomer.model_validate(row) for row in rows]
