"""Refund (avoir) dialog — select items and quantities to return."""

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from services.workers import run_api
from ui import format as fmt
from ui import strings
from ui.styles.tokens import SPACING
from ui.widgets.modal import ModalDialog, show_error


class _RefundItemRow(QWidget):
    """One refundable item line with a quantity spinner."""

    def __init__(self, item: dict, on_changed) -> None:
        super().__init__()
        self.item = item
        self.on_changed = on_changed

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, SPACING["xs"], 0, SPACING["xs"])
        layout.setSpacing(SPACING["sm"])

        name = item["product_name"]
        if item.get("packaging_label"):
            name = f"{name} ({item['packaging_label']})"
        name_label = QLabel(name)
        name_label.setMinimumWidth(180)
        layout.addWidget(name_label, stretch=1)

        avail = QLabel(f"/{item['available']}")
        avail.setObjectName("Muted")
        layout.addWidget(avail)

        self.spin = QSpinBox()
        self.spin.setMinimum(0)
        self.spin.setMaximum(item["available"])
        self.spin.setValue(0)
        self.spin.setFixedWidth(70)
        self.spin.valueChanged.connect(lambda _: on_changed())
        layout.addWidget(self.spin)

        price_label = QLabel(fmt.fmt_money(item["unit_price"]))
        price_label.setFixedWidth(80)
        price_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        layout.addWidget(price_label)

        self.subtotal_label = QLabel("0.00")
        self.subtotal_label.setFixedWidth(90)
        self.subtotal_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.subtotal_label.setStyleSheet("font-weight: 600; background: transparent;")
        layout.addWidget(self.subtotal_label)

    @property
    def quantity(self) -> int:
        return self.spin.value()

    @property
    def subtotal(self) -> Decimal:
        return Decimal(str(self.item["unit_price"])) * self.quantity

    def update_subtotal(self) -> None:
        self.subtotal_label.setText(fmt.fmt_money(self.subtotal))


class RefundDialog(ModalDialog):
    """Select items to refund from a sale, with quantities and reason."""

    def __init__(self, api, sale: dict, parent=None) -> None:
        super().__init__(strings.REFUND_DIALOG_TITLE, parent)
        self.api = api
        self.sale = sale
        self.refund_created = False
        self.refund_amount = Decimal("0.00")
        self._rows: list[_RefundItemRow] = []

        self.setMinimumWidth(600)

        self.reason_input = QLineEdit()
        self.reason_input.setPlaceholderText(strings.REFUND_REASON_PLACEHOLDER)
        reason_label = QLabel(strings.REFUND_REASON_LABEL)
        reason_label.setObjectName("Caption")
        self.content.addWidget(reason_label)
        self.content.addWidget(self.reason_input)

        # Column headers.
        header = QHBoxLayout()
        header.setSpacing(SPACING["sm"])
        for text, width in [
            (strings.REFUND_COL_PRODUCT, 180),
            (strings.REFUND_COL_AVAILABLE, 40),
            (strings.REFUND_COL_QTY, 70),
            (strings.REFUND_COL_PRICE, 80),
            (strings.REFUND_COL_TOTAL, 90),
        ]:
            lbl = QLabel(text)
            lbl.setObjectName("Caption")
            if width == 180:
                header.addWidget(lbl, stretch=1)
            else:
                lbl.setFixedWidth(width)
                header.addWidget(lbl)
        self.content.addLayout(header)

        self._items_container = QVBoxLayout()
        self._items_container.setSpacing(0)
        self.content.addLayout(self._items_container)

        self._loading_label = QLabel(strings.LOADING + "…")
        self._items_container.addWidget(self._loading_label)

        self._total_label = QLabel(strings.REFUND_TOTAL.format(amount="0.00"))
        self._total_label.setStyleSheet(
            "font-weight: 700; font-size: 14px; background: transparent;"
        )
        self.content.addWidget(self._total_label)

        self.ok_button.setText(strings.REFUND_CONFIRM)
        self.ok_button.setEnabled(False)

        run_api(
            lambda: self.api.get_refundable_items(sale["id"]),
            self._on_items_loaded,
            lambda err: show_error(self, err.message),
        )

    def _on_items_loaded(self, items: list) -> None:
        self._loading_label.hide()
        if not items:
            empty = QLabel(strings.REFUND_EMPTY)
            empty.setObjectName("Muted")
            self._items_container.addWidget(empty)
            return

        for item in items:
            row = _RefundItemRow(item, self._on_qty_changed)
            self._rows.append(row)
            self._items_container.addWidget(row)

    def _on_qty_changed(self) -> None:
        total = Decimal("0.00")
        any_selected = False
        for row in self._rows:
            row.update_subtotal()
            total += row.subtotal
            if row.quantity > 0:
                any_selected = True
        self._total_label.setText(strings.REFUND_TOTAL.format(amount=fmt.fmt_money(total)))
        self.ok_button.setEnabled(any_selected)

    def accept(self) -> None:
        items = []
        for row in self._rows:
            if row.quantity > 0:
                items.append({
                    "sale_item_id": row.item["sale_item_id"],
                    "quantity": row.quantity,
                })
        if not items:
            return
        self.ok_button.setEnabled(False)
        reason = self.reason_input.text().strip() or None
        run_api(
            lambda: self.api.create_refund(self.sale["id"], items, reason),
            self._on_created,
            self._on_error,
        )

    def _on_created(self, result: dict) -> None:
        self.refund_created = True
        self.refund_amount = Decimal(str(result.get("total_amount", "0")))
        super().accept()

    def _on_error(self, err) -> None:
        self.ok_button.setEnabled(True)
        show_error(self, err.message)
