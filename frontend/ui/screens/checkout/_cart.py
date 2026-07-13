"""Cart line model and search-result row widget."""

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ui import format as fmt
from ui import strings
from ui.styles.tokens import SPACING
from ui.widgets.badge import Badge
from ui.widgets.thumb import Thumb

_PRICE_FIELDS = {
    "detail": "price_detail",
    "gros": "price_gros",
    "super_gros": "price_super_gros",
}

_CELL_CONTROL_H = 34
_RESULT_THUMB = 60
_CART_THUMB = 44


def _centered_cell(widget: QWidget, left: int = 3, right: int = 3) -> QWidget:
    """Wrap a control so the table centers it vertically in the (taller) row."""
    holder = QWidget()
    layout = QHBoxLayout(holder)
    layout.setContentsMargins(left, 0, right, 0)
    layout.setSpacing(0)
    layout.addWidget(widget)
    return holder


class CartLine:
    def __init__(self, product: dict) -> None:
        self.product = product
        self.packaging: dict | None = None
        self.quantity = 1
        self.level = "detail"
        self.manual_price: Decimal | None = None
        self.discount_percent = 0

    def _price_source(self) -> dict:
        return self.packaging if self.packaging else self.product

    @property
    def unit_price(self) -> Decimal:
        if self.level == "manual" and self.manual_price is not None:
            return self.manual_price
        field = _PRICE_FIELDS.get(self.level, "price_detail")
        return Decimal(self._price_source()[field])

    @property
    def discount_amount(self) -> Decimal:
        gross = self.unit_price * self.quantity
        return (gross * Decimal(self.discount_percent) / 100).quantize(Decimal("0.01"))

    @property
    def total(self) -> Decimal:
        gross = self.unit_price * self.quantity
        return (gross - self.discount_amount).quantize(Decimal("0.01"))

    @property
    def base_units(self) -> int:
        unit_count = self.packaging["unit_count"] if self.packaging else 1
        return self.quantity * unit_count


class _ResultRow(QWidget):
    """Search result: thumbnail, name, stock badge, the three prices."""

    def __init__(self, product: dict) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        sm = SPACING["sm"]
        layout.setContentsMargins(sm, sm, SPACING["md"], sm)
        layout.setSpacing(SPACING["md"])

        thumb = Thumb(_RESULT_THUMB)
        thumb.set_product(product)
        layout.addWidget(thumb)

        info = QVBoxLayout()
        info.setSpacing(2)
        info.setContentsMargins(0, 0, 0, 0)
        name = QLabel(product["name"])
        name.setStyleSheet(
            "font-weight: 600; font-size: 14px; background: transparent;"
        )
        info.addWidget(name)

        prices = QLabel(
            f"{strings.PRICE_DETAIL} {fmt.fmt_money(product['price_detail'])}"
            f"  ·  {strings.PRICE_GROS} {fmt.fmt_money(product['price_gros'])}"
            f"  ·  {strings.PRICE_SUPER_GROS} "
            f"{fmt.fmt_money(product['price_super_gros'])}"
        )
        prices.setObjectName("Muted")
        info.addWidget(prices)
        layout.addLayout(info, stretch=1)

        stock = product["stock_quantity"]
        if stock <= 0:
            stock_badge = Badge(strings.CHECKOUT_OUT_OF_STOCK, "danger")
        elif stock <= product.get("low_stock_threshold", 5):
            stock_badge = Badge(
                strings.CHECKOUT_STOCK_BADGE.format(count=stock), "warning"
            )
        else:
            stock_badge = Badge(
                strings.CHECKOUT_STOCK_BADGE.format(count=stock), "success"
            )
        layout.addWidget(stock_badge, alignment=Qt.AlignmentFlag.AlignVCenter)
