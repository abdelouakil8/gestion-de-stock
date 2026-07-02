"""Custom column types shared by all models."""

from decimal import Decimal

from sqlalchemy import BigInteger
from sqlalchemy.types import TypeDecorator

_CENTS = Decimal("100")
_TWO_PLACES = Decimal("0.01")


class Money(TypeDecorator):
    """Exact monetary storage as integer minor units (cents).

    Python side is always decimal.Decimal; the database column is BIGINT on
    every backend (SQLite today, PostgreSQL later), so storage, comparisons
    and SQL aggregations (SUM for statistics) stay exact — no float ever
    touches a monetary value, per the project's non-negotiable rule.
    """

    impl = BigInteger
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, float):
            raise TypeError("Monetary values must be Decimal, never float")
        value = Decimal(value)
        quantized = value.quantize(_TWO_PLACES)
        if quantized != value:
            raise ValueError(f"Money supports at most 2 decimal places, got {value}")
        return int(quantized * _CENTS)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return Decimal(value) / _CENTS
