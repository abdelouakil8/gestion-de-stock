"""Display formatting helpers — French conventions, Decimal-safe."""

from datetime import datetime
from decimal import Decimal


def fmt_money(value: Decimal | str | int | None, symbol: str = "DA") -> str:
    """1234567.5 -> '1 234 567,50 DA' (French: NBSP thousands, comma decimals)."""
    if value is None:
        amount_str = "0,00"
    else:
        amount = Decimal(str(value)).quantize(Decimal("0.01"))
        text = f"{amount:,.2f}"
        amount_str = text.replace(",", " ").replace(".", ",")
    if symbol:
        return f"{amount_str} {symbol}"
    return amount_str


def fmt_percent(ratio: float, decimals: int = 0) -> str:
    """0.724 -> '72 %'."""
    return f"{ratio * 100:.{decimals}f} %".replace(".", ",")


def fmt_date(value: str | None) -> str:
    """ISO datetime string -> 'JJ/MM/AAAA'."""
    if not value:
        return "—"
    try:
        return datetime.fromisoformat(value).strftime("%d/%m/%Y")
    except ValueError:
        return value


def fmt_datetime(value: str | None) -> str:
    """ISO datetime string -> 'JJ/MM/AAAA HH:MM'."""
    if not value:
        return "—"
    try:
        return datetime.fromisoformat(value).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return value


def fmt_short_datetime(value: str | None) -> str:
    """ISO datetime string -> 'JJ/MM HH:MM' (compact, no year)."""
    if not value:
        return "—"
    try:
        return datetime.fromisoformat(value).strftime("%d/%m %H:%M")
    except ValueError:
        return value
