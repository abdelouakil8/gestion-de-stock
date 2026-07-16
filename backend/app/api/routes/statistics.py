from datetime import date, datetime, time
from uuid import UUID

from fastapi import APIRouter, Query
from fastapi.responses import Response
from sqlalchemy import select

from app.api.deps import DbDep, OwnerPinDep
from app.core.exceptions import NotFoundError
from app.models import Product
from app.schemas.statistics import (
    AssociationRule,
    AssociationsResult,
    CategoryStat,
    CustomerInsights,
    CustomerStats,
    DailyPoint,
    DeadStockItem,
    FinancialSnapshot,
    FrequentItemset,
    InventoryStats,
    MarginAnalysis,
    OverviewStats,
    PaymentMethodBreakdown,
    ProductProfitability,
    ProductRef,
    ProductStats,
    ProductVelocity,
    SalesPatterns,
    StatsSummary,
    StockTurnover,
    TopCustomer,
    TopProduct,
)
from app.services import customers, profitability, reports, statistics, stores, velocity
from app.services import settings as settings_service
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
    sort: str = Query(default="quantity", pattern="^(quantity|profit)$"),
) -> list:
    """Best sellers by units sold (default) or by total gross profit."""
    start, end = _day_bounds(date_from, date_to)
    return statistics.top_products(db, store_id, start, end, limit=limit, sort=sort)


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
    "/payment-methods",
    response_model=list[PaymentMethodBreakdown],
    dependencies=[OwnerPinDep],
)
def payment_methods(store_id: UUID, date_from: date, date_to: date, db: DbDep) -> list:
    """Revenue breakdown by payment method (cash/card/mobile/other)."""
    start, end = _day_bounds(date_from, date_to)
    return statistics.payment_method_breakdown(db, store_id, start, end)


@router.get(
    "/daily-evolution", response_model=list[DailyPoint], dependencies=[OwnerPinDep]
)
def daily_evolution(store_id: UUID, date_from: date, date_to: date, db: DbDep) -> list:
    """Revenue + profit per calendar day over the range (zero-filled)."""
    start, end = _day_bounds(date_from, date_to)
    return statistics.daily_evolution(db, store_id, start, end)


@router.get("/inventory", response_model=InventoryStats, dependencies=[OwnerPinDep])
def inventory(store_id: UUID, db: DbDep):
    """Capital tied up in stock (at cost and at retail) and stock health."""
    return statistics.inventory_stats(db, store_id)


@router.get(
    "/dead-stock", response_model=list[DeadStockItem], dependencies=[OwnerPinDep]
)
def dead_stock(
    store_id: UUID,
    db: DbDep,
    days: int = Query(default=60, ge=1, le=365),
    limit: int = Query(default=20, ge=1, le=100),
) -> list:
    """Active products still in stock that have not sold in `days` days."""
    return statistics.dead_stock(db, store_id, days=days, limit=limit)


@router.get(
    "/category-breakdown",
    response_model=list[CategoryStat],
    dependencies=[OwnerPinDep],
)
def category_breakdown(
    store_id: UUID, date_from: date, date_to: date, db: DbDep
) -> list:
    """Revenue/profit/quantity by product category over the range."""
    start, end = _day_bounds(date_from, date_to)
    return statistics.category_breakdown(db, store_id, start, end)


@router.get("/sales-patterns", response_model=SalesPatterns, dependencies=[OwnerPinDep])
def sales_patterns(store_id: UUID, date_from: date, date_to: date, db: DbDep):
    """Busy hours and weekdays (store-local) over the range."""
    start, end = _day_bounds(date_from, date_to)
    return statistics.sales_patterns(db, store_id, start, end)


@router.get(
    "/customer-insights",
    response_model=CustomerInsights,
    dependencies=[OwnerPinDep],
)
def customer_insights(store_id: UUID, date_from: date, date_to: date, db: DbDep):
    """Active / new / returning customers and guest sales over the range."""
    start, end = _day_bounds(date_from, date_to)
    return statistics.customer_insights(db, store_id, start, end)


@router.get(
    "/financial-snapshot",
    response_model=FinancialSnapshot,
    dependencies=[OwnerPinDep],
)
def financial_snapshot(store_id: UUID, db: DbDep):
    """Outstanding customer credit and supplier debt (all-time balances)."""
    return statistics.financial_snapshot(db, store_id)


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
    
    import random
    if len(basket_list) > 10000:
        # Cap baskets to prevent OOM/CPU lockup on 2GB devices, 10k is statistically identical
        basket_list = random.sample(basket_list, 10000)
        
    result = apriori.mine(
        basket_list, min_support=min_support, min_confidence=min_confidence, max_len=3
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


@router.get(
    "/profitability",
    response_model=list[ProductProfitability],
    dependencies=[OwnerPinDep],
)
def profitability_ranking(
    store_id: UUID,
    date_from: date,
    date_to: date,
    db: DbDep,
    limit: int = Query(default=20, ge=1, le=100),
    sort: str = Query(default="profit", pattern="^(profit|margin_pct)$"),
) -> list:
    start, end = _day_bounds(date_from, date_to)
    return profitability.product_profitability(
        db, store_id, start, end, limit=limit, sort=sort
    )


@router.get(
    "/margin-analysis",
    response_model=MarginAnalysis,
    dependencies=[OwnerPinDep],
)
def margin_analysis(store_id: UUID, date_from: date, date_to: date, db: DbDep):
    start, end = _day_bounds(date_from, date_to)
    return profitability.margin_analysis(db, store_id, start, end)


@router.get(
    "/velocity",
    response_model=list[ProductVelocity],
    dependencies=[OwnerPinDep],
)
def velocity_ranking(
    store_id: UUID,
    date_from: date,
    date_to: date,
    db: DbDep,
    limit: int = Query(default=20, ge=1, le=100),
    sort: str = Query(default="velocity", pattern="^(velocity|days_of_stock)$"),
) -> list:
    start, end = _day_bounds(date_from, date_to)
    return velocity.product_velocity(db, store_id, start, end, limit=limit, sort=sort)


@router.get(
    "/stock-turnover",
    response_model=StockTurnover,
    dependencies=[OwnerPinDep],
)
def turnover(store_id: UUID, date_from: date, date_to: date, db: DbDep):
    start, end = _day_bounds(date_from, date_to)
    return velocity.stock_turnover(db, store_id, start, end)


@router.get("/report.pdf", dependencies=[OwnerPinDep])
def report_pdf(store_id: UUID, date_from: date, date_to: date, db: DbDep):
    start, end = _day_bounds(date_from, date_to)
    s = settings_service.get_settings(db, store_id)
    lang = (s.ui_language or "fr") if s else "fr"
    pdf_bytes = reports.build_summary_report_pdf(
        db, store_id, start, end, language=lang
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="rapport.pdf"'},
    )


@router.get("/daily-report.pdf", dependencies=[OwnerPinDep])
def daily_report_pdf(store_id: UUID, date: date, db: DbDep):  # noqa: A002
    """End-of-day A4 report for one calendar day (any past date)."""
    store = stores.get_store(db, store_id)
    if store is None:
        raise NotFoundError("boutique", store_id)
    store_settings = settings_service.get_settings(db, store_id)
    pdf_bytes = reports.build_daily_report_pdf(
        db, store_id, date, store, store_settings
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="rapport_journalier_{date}.pdf"'
        },
    )


@router.get("/comparison-report.pdf", dependencies=[OwnerPinDep])
def comparison_report_pdf(
    store_id: UUID,
    a_from: date,
    a_to: date,
    b_from: date,
    b_to: date,
    db: DbDep,
):
    """Two-period comparison report (metrics + top products) as a PDF."""
    a_start, a_end = _day_bounds(a_from, a_to)
    b_start, b_end = _day_bounds(b_from, b_to)
    s = settings_service.get_settings(db, store_id)
    lang = (s.ui_language or "fr") if s else "fr"
    pdf_bytes = reports.build_comparison_report_pdf(
        db, store_id, a_start, a_end, b_start, b_end, language=lang
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="comparaison.pdf"'},
    )


@router.get("/report.xlsx", dependencies=[OwnerPinDep])
def report_xlsx(store_id: UUID, date_from: date, date_to: date, db: DbDep):
    start, end = _day_bounds(date_from, date_to)
    s = settings_service.get_settings(db, store_id)
    lang = (s.ui_language or "fr") if s else "fr"
    xlsx_bytes = reports.build_summary_report_xlsx(
        db, store_id, start, end, language=lang
    )
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="rapport.xlsx"'},
    )
