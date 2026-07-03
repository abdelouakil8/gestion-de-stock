"""Display formatting helpers — French conventions, Decimal-safe."""

from datetime import datetime
from decimal import Decimal


def fmt_money(value: Decimal | str | int | None) -> str:
    """1234567.5 -> '1 234 567,50' (French: NBSP thousands, comma decimals)."""
    if value is None:
        return "0,00"
    amount = Decimal(str(value)).quantize(Decimal("0.01"))
    text = f"{amount:,.2f}"
    return text.replace(",", " ").replace(".", ",")


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
