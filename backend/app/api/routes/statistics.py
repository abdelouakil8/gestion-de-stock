from datetime import date, datetime, time
from uuid import UUID

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.deps import DbDep, OwnerPinDep
from app.core.exceptions import NotFoundError
from app.models import Product
from app.schemas.statistics import (
    AssociationRule,
    AssociationsResult,
    CustomerStats,
    FrequentItemset,
    OverviewStats,
    ProductRef,
    ProductStats,
    StatsSummary,
    TopCustomer,
    TopProduct,
)
from app.services import customers, statistics
from app.services.analysis import apriori, baskets

router = APIRouter()

# Statistics expose profit (derived from cost_price) — owner-only, PIN-gated.


def _day_bounds(date_from: date, date_to: date) -> tuple[datetime, datetime]:
    """Merchant-picked dates → inclusive datetime range (UTC)."""
    return (
        datetime.combine(date_from, time.min),
        datetime.combine(date_to, time.max),
    )


@router.get("/summary", response_model=StatsSummary, dependencies=[OwnerPinDep])
def summary(store_id: UUID, date_from: date, date_to: date, db: DbDep):
    start, end = _day_bounds(date_from, date_to)
    return statistics.sales_summary(db, store_id, start, end)


@router.get(
    "/top-products", response_model=list[TopProduct], dependencies=[OwnerPinDep]
)
def top_products(
    store_id: UUID,
    date_from: date,
    date_to: date,
    db: DbDep,
    limit: int = Query(default=10, ge=1, le=100),
) -> list:
    start, end = _day_bounds(date_from, date_to)
    return statistics.top_products(db, store_id, start, end, limit=limit)


@router.get("/overview", response_model=OverviewStats, dependencies=[OwnerPinDep])
def overview(store_id: UUID, db: DbDep):
    """Today / this week / this month / this year, each with the previous
    calendar period for comparison (store timezone = local machine)."""
    return statistics.overview(db, store_id)


@router.get(
    "/products/{product_id}", response_model=ProductStats, dependencies=[OwnerPinDep]
)
def product_stats(store_id: UUID, product_id: UUID, db: DbDep):
    """Units sold, revenue and profit: today, 7/30/365 days, all-time."""
    stats = statistics.product_stats(db, store_id, product_id)
    if stats is None:
        raise NotFoundError("produit", product_id)
    return stats


@router.get(
    "/top-customers", response_model=list[TopCustomer], dependencies=[OwnerPinDep]
)
def top_customers(
    store_id: UUID,
    date_from: date,
    date_to: date,
    db: DbDep,
    limit: int = Query(default=10, ge=1, le=100),
) -> list:
    """Customers ranked by revenue over the date range."""
    start, end = _day_bounds(date_from, date_to)
    return customers.top_customers(db, store_id, start, end, limit=limit)


@router.get(
    "/customers/{customer_id}",
    response_model=CustomerStats,
    dependencies=[OwnerPinDep],
)
def customer_stats(customer_id: UUID, db: DbDep):
    """Lifetime revenue, profit, sales count, balance, last purchase."""
    stats = customers.customer_stats(db, customer_id)
    if stats is None:
        raise NotFoundError("client", customer_id)
    return stats


@router.get(
    "/associations", response_model=AssociationsResult, dependencies=[OwnerPinDep]
)
def associations(
    store_id: UUID,
    date_from: date,
    date_to: date,
    db: DbDep,
    min_support: float = Query(default=0.05, gt=0, le=1),
    min_confidence: float = Query(default=0.3, gt=0, le=1),
):
    """Market-basket analysis (Apriori): frequent itemsets and association
    rules (antecedent → consequent, support, confidence, lift) mined from
    the sale baskets of the period, product names resolved."""
    start, end = _day_bounds(date_from, date_to)
    basket_list = baskets.sale_baskets(db, store_id, start, end)
    result = apriori.mine(
        basket_list, min_support=min_support, min_confidence=min_confidence
    )

    # Resolve product names once for every id in the result.
    ids = set()
    for itemset in result.itemsets:
        ids |= itemset.items
    names = {
        row.id: row.name
        for row in db.execute(
            select(Product.id, Product.name).where(Product.id.in_(ids))
        ).all()
    }

    def refs(items: frozenset) -> list[ProductRef]:
        return sorted(
            (
                ProductRef(product_id=pid, name=names.get(pid, "Produit supprimé"))
                for pid in items
            ),
            key=lambda ref: ref.name,
        )

    return AssociationsResult(
        basket_count=result.basket_count,
        min_support=min_support,
        min_confidence=min_confidence,
        itemsets=[
            FrequentItemset(products=refs(i.items), support=i.support, count=i.count)
            for i in result.itemsets
        ],
        rules=[
            AssociationRule(
                antecedent=refs(r.antecedent),
                consequent=refs(r.consequent),
                support=r.support,
                confidence=r.confidence,
                lift=r.lift,
            )
            for r in result.rules
        ],
    )
