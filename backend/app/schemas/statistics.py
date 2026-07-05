from datetime import datetime
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
