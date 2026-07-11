from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class StatsSummary(BaseModel):
    """Revenue and gross profit over a date range."""

    model_config = ConfigDict(from_attributes=True)

    revenue: Decimal
    gross_profit: Decimal
    sales_count: int
    total_discounts: Decimal = Decimal("0.00")
    date_from: datetime
    date_to: datetime


class PaymentMethodBreakdown(BaseModel):
    """Revenue split by payment method for a date range."""

    payment_method: str
    total: Decimal
    count: int


class TopProduct(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: UUID
    name: str
    quantity_sold: int
    revenue: Decimal
    profit: Decimal = Decimal("0.00")


# ------------------------------------------------------------ Phase 6


class PeriodStats(BaseModel):
    """Units/revenue/profit of one product over one named period."""

    period: str
    date_from: datetime | None  # None = all-time (no lower bound)
    date_to: datetime
    units_sold: int
    revenue: Decimal
    profit: Decimal


class ProductStats(BaseModel):
    product_id: UUID
    name: str
    periods: list[PeriodStats]


class OverviewPeriod(BaseModel):
    """One calendar period (current) with its previous period for comparison."""

    period: str  # today | this_week | this_month | this_year
    current: StatsSummary
    previous: StatsSummary


class OverviewStats(BaseModel):
    periods: list[OverviewPeriod]


class CustomerStats(BaseModel):
    """Per-customer analytics — owner view (includes profit)."""

    customer_id: UUID
    name: str
    phone: str
    total_revenue: Decimal
    total_profit: Decimal
    sales_count: int
    outstanding_balance: Decimal
    last_purchase_at: datetime | None


class TopCustomer(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    customer_id: UUID
    name: str
    phone: str
    revenue: Decimal
    sales_count: int


class ProductRef(BaseModel):
    """Product identity inside association-analysis results."""

    product_id: UUID
    name: str


class FrequentItemset(BaseModel):
    products: list[ProductRef]
    support: float
    count: int


class AssociationRule(BaseModel):
    antecedent: list[ProductRef]
    consequent: list[ProductRef]
    support: float
    confidence: float
    lift: float


class AssociationsResult(BaseModel):
    basket_count: int
    min_support: float
    min_confidence: float
    itemsets: list[FrequentItemset]
    rules: list[AssociationRule]


# ---------------------------------------- Phase 12: dashboard analytics


class DailyPoint(BaseModel):
    """One calendar day of the evolution series (revenue + profit)."""

    day: date
    revenue: Decimal
    profit: Decimal


class InventoryStats(BaseModel):
    """Owner snapshot of stock value and health (derives from cost_price)."""

    stock_value_cost: Decimal  # capital tied up at cost
    stock_value_retail: Decimal  # value at the détail price
    product_count: int
    active_count: int
    out_of_stock_count: int
    low_stock_count: int


class DeadStockItem(BaseModel):
    """A product still in stock that has not sold in the window."""

    model_config = ConfigDict(from_attributes=True)

    product_id: UUID
    name: str
    category_name: str | None = None  # None = uncategorised
    image_path: str | None = None  # None = no product image
    stock_quantity: int
    tied_capital: Decimal  # cost_price * stock_quantity
    last_sold_at: datetime | None
    days_since: int | None  # None = never sold


class CategoryStat(BaseModel):
    """Revenue/profit/quantity of one category over a date range."""

    model_config = ConfigDict(from_attributes=True)

    category_id: UUID | None  # None = uncategorised
    name: str | None
    revenue: Decimal
    profit: Decimal
    quantity: int


class HourBucket(BaseModel):
    hour: int  # 0..23, store-local time
    revenue: Decimal
    sales_count: int


class WeekdayBucket(BaseModel):
    weekday: int  # 0=Monday .. 6=Sunday (French convention)
    revenue: Decimal
    sales_count: int


class SalesPatterns(BaseModel):
    """When the shop is busy: by hour of day and by weekday (store-local)."""

    hourly: list[HourBucket]
    weekday: list[WeekdayBucket]


class CustomerInsights(BaseModel):
    """Who bought over the range: active, new, returning, and guest sales."""

    active_customers: int
    new_customers: int
    returning_customers: int
    guest_sales_count: int


class FinancialSnapshot(BaseModel):
    """Money owed to and by the shop, right now (all-time balances)."""

    customer_credit_total: Decimal  # money customers still owe us
    customer_credit_count: int
    supplier_debt_total: Decimal  # money we still owe suppliers
    supplier_debt_count: int
