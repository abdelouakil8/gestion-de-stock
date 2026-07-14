"""Supplier dialogs, purchase-order form, and shared helpers."""

from decimal import Decimal

import qtawesome as qta
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from services.workers import run_api
from ui import format as fmt
from ui import strings
from ui.styles.tokens import NEUTRAL, SPACING
from ui.widgets.data_table import DataTable
from ui.widgets.modal import ModalDialog, show_error
from ui.widgets.product_search import ProductSearchBox


def _money(value) -> Decimal:
    return Decimal(str(value)) if value is not None else Decimal("0.00")


def _order_status(order: dict) -> tuple[str, str, str]:
    """(filter_key, badge_label, badge_kind) for a purchase order."""
    total = _money(order.get("total_amount"))
    paid = _money(order.get("paid_amount"))
    balance = _money(order.get("balance", total - paid))
    if balance <= 0:
        return ("paid", strings.PO_STATUS_PAID, "success")
    if paid <= 0:
        return ("unpaid", strings.PO_STATUS_UNPAID, "danger")
    return ("partial", strings.PO_STATUS_PARTIAL, "warning")


def _order_ref(order: dict) -> str:
    """Short human reference for an order (first 8 chars of the id)."""
    return str(order.get("id", ""))[:8].upper()


class SupplierDialog(ModalDialog):
    """Create / edit a supplier."""

    def __init__(self, api, store_id, supplier=None, parent=None):
        title = (
            strings.SUPPLIER_DIALOG_EDIT if supplier else strings.SUPPLIER_DIALOG_NEW
        )
        super().__init__(title, parent)
        self.api = api
        self.store_id = store_id
        self.supplier = supplier
        self.result = None

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText(strings.SUPPLIER_NAME)
        self.content.addWidget(self.name_input)

        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText(strings.SUPPLIER_PHONE)
        self.content.addWidget(self.phone_input)

        self.note_input = QLineEdit()
        self.note_input.setPlaceholderText(strings.SUPPLIER_NOTE)
        self.content.addWidget(self.note_input)

        if supplier:
            self.name_input.setText(supplier.get("name", ""))
            self.phone_input.setText(supplier.get("phone", ""))
            self.note_input.setText(supplier.get("note", "") or "")

        self.ok_button.setText(strings.SAVE)

    def accept(self):
        name = self.name_input.text().strip()
        phone = self.phone_input.text().strip()
        if not name or not phone:
            show_error(self, strings.REQUIRED_FIELD)
            return
        note = self.note_input.text().strip() or None
        self.ok_button.setEnabled(False)
        if self.supplier:
            run_api(
                lambda: self.api.update_supplier(
                    self.supplier["id"],
                    {"name": name, "phone": phone, "note": note},
                ),
                self._done,
                self._err,
            )
        else:
            run_api(
                lambda: self.api.create_supplier(
                    {
                        "store_id": self.store_id,
                        "name": name,
                        "phone": phone,
                        "note": note,
                    }
                ),
                self._done,
                self._err,
            )

    def _done(self, result):
        self.result = result
        super().accept()

    def _err(self, err):
        self.ok_button.setEnabled(True)
        show_error(self, err.message)


class SupplierPaymentDialog(ModalDialog):
    """Record a payment on a purchase order with an outstanding balance."""

    def __init__(self, api, order: dict, parent=None):
        super().__init__(strings.PO_RECORD_PAYMENT, parent)
        self.api = api
        self.order = order
        self.result_order: dict | None = None
        self.balance = _money(order.get("balance")) or (
            _money(order.get("total_amount")) - _money(order.get("paid_amount"))
        )

        info = QLabel(
            strings.PAYMENT_RECORD_BALANCE.format(balance=fmt.fmt_money(self.balance))
        )
        info.setObjectName("Secondary")
        self.content.addWidget(info)

        amount_row = QHBoxLayout()
        amount_row.addWidget(QLabel(strings.PAYMENT_AMOUNT_LABEL))
        self.amount_input = QDoubleSpinBox()
        self.amount_input.setDecimals(2)
        self.amount_input.setRange(0.0, float(self.balance))
        self.amount_input.setValue(float(self.balance))
        self.amount_input.setAlignment(
            Qt.AlignmentFlag.AlignTrailing | Qt.AlignmentFlag.AlignVCenter
        )
        amount_row.addWidget(self.amount_input, stretch=1)
        self.content.addLayout(amount_row)

        self.ok_button.setText(strings.PAYMENT_CONFIRM)
        self.amount_input.setFocus()
        self.amount_input.selectAll()

    def accept(self):
        amount = Decimal(f"{self.amount_input.value():.2f}")
        if amount <= 0:
            show_error(self, strings.PAYMENT_AMOUNT_REQUIRED)
            return
        if amount > self.balance:
            show_error(self, strings.PAYMENT_AMOUNT_TOO_HIGH)
            return
        self.ok_button.setEnabled(False)
        run_api(
            lambda: self.api.record_supplier_payment(
                self.order["id"], f"{amount:.2f}", "cash"
            ),
            self._done,
            self._err,
        )

    def _done(self, order):
        self.result_order = order
        super().accept()

    def _err(self, err):
        self.ok_button.setEnabled(True)
        show_error(self, err.message)


class _POLineRow(QWidget):
    """One editable order line: product search, quantity, unit cost, total."""

    def __init__(self, api, store_id, on_remove, on_change, parent=None):
        super().__init__(parent)
        self.api = api
        self.store_id = store_id
        self._on_change = on_change
        self.product_id: str | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACING["xs"])

        self.product_search = ProductSearchBox(api, store_id, self._on_product_selected)
        layout.addWidget(self.product_search, stretch=1)

        self.qty = QSpinBox()
        self.qty.setRange(1, 9999)
        self.qty.setValue(1)
        self.qty.setFixedWidth(80)
        self.qty.setAlignment(
            Qt.AlignmentFlag.AlignTrailing | Qt.AlignmentFlag.AlignVCenter
        )
        self.qty.valueChanged.connect(lambda _=None: self._recompute())
        layout.addWidget(self.qty)

        self.unit_cost = QDoubleSpinBox()
        self.unit_cost.setDecimals(2)
        self.unit_cost.setRange(0.0, 9_999_999.99)
        self.unit_cost.setFixedWidth(120)
        self.unit_cost.setAlignment(
            Qt.AlignmentFlag.AlignTrailing | Qt.AlignmentFlag.AlignVCenter
        )
        self.unit_cost.valueChanged.connect(lambda _=None: self._recompute())
        layout.addWidget(self.unit_cost)

        self.total_label = QLabel(fmt.fmt_money(0))
        self.total_label.setFixedWidth(120)
        self.total_label.setAlignment(
            Qt.AlignmentFlag.AlignTrailing | Qt.AlignmentFlag.AlignVCenter
        )
        layout.addWidget(self.total_label)

        remove = QPushButton(qta.icon("fa5s.trash", color=NEUTRAL["500"]), "")
        remove.setObjectName("Ghost")
        remove.setFixedWidth(36)
        remove.setToolTip(strings.PACKAGING_REMOVE)
        remove.clicked.connect(lambda: on_remove(self))
        layout.addWidget(remove)

    def _on_product_selected(self, product: dict) -> None:
        self.product_id = str(product["id"])
        self.product_search.set_text(product["name"])
        run_api(
            lambda: self.api.get_product_details(self.product_id),
            self._on_details,
            lambda err: None,
        )
        self.unit_cost.setFocus()
        self.unit_cost.selectAll()
        self._recompute()

    def _on_details(self, details: object) -> None:
        cost = details.get("cost_price") if isinstance(details, dict) else None
        if cost is not None and self.unit_cost.value() == 0:
            self.unit_cost.setValue(float(cost))

    def set_product(self, product: dict) -> None:
        """Prefill this row with a product (used for pre-filled first lines)."""
        self._on_product_selected(product)

    def _recompute(self) -> None:
        self.total_label.setText(fmt.fmt_money(self.line_total()))
        self._on_change()

    def line_total(self) -> Decimal:
        return (Decimal(f"{self.unit_cost.value():.2f}") * self.qty.value()).quantize(
            Decimal("0.01")
        )

    def is_valid(self) -> bool:
        return self.product_id is not None

    def payload(self) -> dict:
        return {
            "product_id": self.product_id,
            "quantity": self.qty.value(),
            "unit_cost": f"{self.unit_cost.value():.2f}",
        }


class PurchaseOrderDialog(ModalDialog):
    """Create a purchase order (bon de réception) — updates stock on submit."""

    def __init__(
        self,
        api,
        store_id,
        suppliers: list[dict],
        prefill_supplier_id=None,
        prefill_product: dict | None = None,
        parent=None,
    ):
        super().__init__(strings.PO_DIALOG_NEW, parent)
        self.api = api
        self.store_id = store_id
        self.result_order: dict | None = None
        self._rows: list[_POLineRow] = []
        self.setMinimumWidth(720)

        supplier_row = QHBoxLayout()
        supplier_row.addWidget(QLabel(strings.PO_SUPPLIER_LABEL))
        self.supplier_combo = QComboBox()
        for supplier in suppliers:
            self.supplier_combo.addItem(supplier["name"], str(supplier["id"]))
        if prefill_supplier_id is not None:
            index = self.supplier_combo.findData(str(prefill_supplier_id))
            if index >= 0:
                self.supplier_combo.setCurrentIndex(index)
            self.supplier_combo.setEnabled(False)
        supplier_row.addWidget(self.supplier_combo, stretch=1)
        self.content.addLayout(supplier_row)

        lines_title = QLabel(strings.PO_LINES_SECTION)
        lines_title.setObjectName("SectionTitle")
        self.content.addWidget(lines_title)

        self._rows_holder = QWidget()
        self._rows_box = QVBoxLayout(self._rows_holder)
        self._rows_box.setContentsMargins(0, 0, 0, 0)
        self._rows_box.setSpacing(SPACING["xs"])
        self._rows_box.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._rows_holder)
        scroll.setMinimumHeight(200)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.content.addWidget(scroll)

        add_line = QPushButton(
            qta.icon("fa5s.plus", color=NEUTRAL["600"]), strings.PO_ADD_LINE_ROW
        )
        add_line.setObjectName("Ghost")
        add_line.clicked.connect(lambda: self._add_row())
        self.content.addWidget(add_line)

        divider = QFrame()
        divider.setObjectName("HDivider")
        divider.setFixedHeight(1)
        self.content.addWidget(divider)
        total_row = QHBoxLayout()
        total_row.addStretch(1)
        total_caption = QLabel(strings.PO_TOTAL)
        total_caption.setObjectName("Caption")
        total_row.addWidget(total_caption)
        self.total_label = QLabel(fmt.fmt_money(0))
        self.total_label.setObjectName("TotalAmount")
        total_row.addWidget(self.total_label)
        self.content.addLayout(total_row)

        self.ok_button.setText(strings.PO_SUBMIT_UPDATE_STOCK)

        first = self._add_row()
        if prefill_product is not None:
            first.set_product(prefill_product)

    def _add_row(self) -> _POLineRow:
        row = _POLineRow(self.api, self.store_id, self._remove_row, self._refresh_total)
        self._rows.append(row)
        self._rows_box.insertWidget(self._rows_box.count() - 1, row)
        self.fit_to_content()
        return row

    def _remove_row(self, row: _POLineRow) -> None:
        if row in self._rows:
            self._rows.remove(row)
        self._rows_box.removeWidget(row)
        row.deleteLater()
        self._refresh_total()
        self.fit_to_content()

    def _refresh_total(self) -> None:
        total = sum((row.line_total() for row in self._rows), Decimal("0.00"))
        self.total_label.setText(fmt.fmt_money(total))

    def accept(self) -> None:
        supplier_id = self.supplier_combo.currentData()
        if not supplier_id:
            show_error(self, strings.PO_SELECT_SUPPLIER)
            return
        items = [row.payload() for row in self._rows if row.is_valid()]
        if not items:
            show_error(self, strings.PO_NEED_ONE_LINE)
            return
        payload = {
            "store_id": str(self.store_id),
            "supplier_id": str(supplier_id),
            "items": items,
        }
        self.ok_button.setEnabled(False)
        run_api(
            lambda: self.api.create_purchase_order(payload),
            self._done,
            self._err,
        )

    def _done(self, order):
        self.result_order = order
        super().accept()

    def _err(self, err):
        self.ok_button.setEnabled(True)
        show_error(self, err.message)


class PurchaseOrderDetailsDialog(ModalDialog):
    """Read-only view of one purchase order: header + line items."""

    def __init__(
        self, order: dict, supplier_name: str, product_names: dict, parent=None
    ):
        super().__init__(strings.PO_DIALOG_DETAILS, parent)
        self.setMinimumWidth(560)

        _key, status_label, _kind = _order_status(order)
        header = QLabel(
            f"{supplier_name}  ·  {strings.PO_GCOL_REF} {_order_ref(order)}  ·  "
            f"{fmt.fmt_date(order.get('created_at'))}"
        )
        header.setObjectName("SectionTitle")
        self.content.addWidget(header)

        total = _money(order.get("total_amount"))
        paid = _money(order.get("paid_amount"))
        balance = _money(order.get("balance", total - paid))
        summary = QLabel(
            f"{strings.PO_GCOL_TOTAL} {fmt.fmt_money(total)}   ·   "
            f"{strings.PO_GCOL_PAID} {fmt.fmt_money(paid)}   ·   "
            f"{strings.PO_GCOL_BALANCE} {fmt.fmt_money(balance)}   ·   {status_label}"
        )
        summary.setObjectName("Secondary")
        self.content.addWidget(summary)

        table = DataTable(
            [
                strings.PO_COL_PRODUCT,
                strings.PO_COL_QTY,
                strings.PO_COL_UNIT_COST,
                strings.PO_COL_TOTAL,
            ]
        )
        rows = []
        for item in order.get("items", []):
            name = product_names.get(
                str(item.get("product_id")), strings.PO_COL_PRODUCT
            )
            rows.append(
                [
                    name,
                    str(item.get("quantity", "")),
                    fmt.fmt_money(item.get("unit_cost")),
                    fmt.fmt_money(item.get("line_total")),
                ]
            )
        table.set_rows(rows)
        table.setMinimumHeight(200)
        self.content.addWidget(table)

        self.cancel_button.hide()
        self.ok_button.setText(strings.CLOSE)
