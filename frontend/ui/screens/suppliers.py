"""Fournisseurs screen — structurally mirrors customers.py (list + detail)."""

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from services.workers import run_api
from ui import format as fmt
from ui import strings
from ui.styles.tokens import SPACING
from ui.widgets.card import SectionCard, StatCard
from ui.widgets.data_table import DataTable
from ui.widgets.modal import ModalDialog, show_error
from ui.widgets.states import EmptyState
from ui.widgets.toast import show_toast


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
                    {"store_id": self.store_id, "name": name, "phone": phone, "note": note}
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


class SuppliersScreen(QWidget):
    def __init__(self, api, store_id, parent=None):
        super().__init__(parent)
        self.api = api
        self.store_id = store_id
        self._suppliers: list[dict] = []

        layout = QHBoxLayout(self)
        layout.setContentsMargins(*[SPACING["xl"]] * 4)
        layout.setSpacing(SPACING["lg"])

        left = QVBoxLayout()
        left_header = QHBoxLayout()
        title = QLabel(strings.SUPPLIERS_TITLE)
        title.setObjectName("ScreenTitle")
        left_header.addWidget(title)
        left_header.addStretch(1)
        new_btn = QPushButton(strings.SUPPLIERS_NEW)
        new_btn.setObjectName("Primary")
        new_btn.clicked.connect(self._new_supplier)
        left_header.addWidget(new_btn)
        left.addLayout(left_header)

        self.search = QLineEdit()
        self.search.setPlaceholderText(strings.SUPPLIERS_SEARCH_PLACEHOLDER)
        self.search.textChanged.connect(self._filter)
        left.addWidget(self.search)

        self.supplier_list = QListWidget()
        self.supplier_list.currentRowChanged.connect(self._on_select)
        left.addWidget(self.supplier_list, stretch=1)
        layout.addLayout(left, stretch=1)

        right = QVBoxLayout()
        self.detail_stack = QStackedWidget()
        self.detail_empty = EmptyState(
            "fa5s.truck",
            strings.SUPPLIERS_EMPTY,
            strings.SUPPLIERS_EMPTY_HINT,
        )
        self.detail_content = QWidget()
        self._build_detail()
        self.detail_stack.addWidget(self.detail_empty)
        self.detail_stack.addWidget(self.detail_content)
        right.addWidget(self.detail_stack, stretch=1)
        layout.addLayout(right, stretch=2)

    def _build_detail(self):
        layout = QVBoxLayout(self.detail_content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACING["md"])

        self.detail_name = QLabel()
        self.detail_name.setObjectName("ScreenTitle")
        layout.addWidget(self.detail_name)

        stats_row = QHBoxLayout()
        self.stat_orders = StatCard(strings.SUPPLIER_STAT_ORDERS)
        self.stat_total = StatCard(strings.SUPPLIER_STAT_TOTAL)
        self.stat_balance = StatCard(strings.SUPPLIER_STAT_BALANCE)
        stats_row.addWidget(self.stat_orders)
        stats_row.addWidget(self.stat_total)
        stats_row.addWidget(self.stat_balance)
        layout.addLayout(stats_row)

        history_card = SectionCard(strings.SUPPLIER_ORDERS_HISTORY, "fa5s.boxes")
        self.orders_table = DataTable(
            [
                strings.SUPPLIER_COL_DATE,
                strings.SUPPLIER_COL_TOTAL,
                strings.SUPPLIER_COL_PAID,
                strings.SUPPLIER_COL_BALANCE,
            ]
        )
        self.orders_table.setMinimumHeight(200)
        history_card.body.addWidget(self.orders_table)
        layout.addWidget(history_card, stretch=1)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        edit_btn = QPushButton(strings.EDIT)
        edit_btn.setObjectName("Secondary")
        edit_btn.clicked.connect(self._edit_supplier)
        btn_row.addWidget(edit_btn)
        layout.addLayout(btn_row)

    def refresh(self):
        run_api(
            lambda: self.api.list_suppliers(self.store_id),
            self._on_list,
            lambda err: show_error(self, err.message),
        )

    def _on_list(self, suppliers):
        self._suppliers = list(suppliers or [])
        self._filter()

    def _filter(self):
        q = self.search.text().strip().lower()
        self.supplier_list.clear()
        for s in self._suppliers:
            if q and q not in (s.get("name", "") + s.get("phone", "")).lower():
                continue
            item = QListWidgetItem(f"{s['name']}  ·  {s['phone']}")
            item.setData(Qt.ItemDataRole.UserRole, s)
            self.supplier_list.addItem(item)
        if self.supplier_list.count() == 0:
            self.detail_stack.setCurrentWidget(self.detail_empty)

    def _on_select(self, row):
        if row < 0:
            self.detail_stack.setCurrentWidget(self.detail_empty)
            return
        item = self.supplier_list.item(row)
        supplier = item.data(Qt.ItemDataRole.UserRole)
        self._show_detail(supplier)

    def _show_detail(self, supplier):
        self.detail_name.setText(f"{supplier['name']}  ·  {supplier['phone']}")
        self.detail_stack.setCurrentWidget(self.detail_content)
        run_api(
            lambda: self.api.list_purchase_orders(
                self.store_id, supplier_id=supplier["id"]
            ),
            lambda orders, s=supplier: self._on_orders(s, orders),
            lambda err: None,
        )

    def _on_orders(self, supplier, orders):
        orders = list(orders or [])
        total = sum(Decimal(str(o["total_amount"])) for o in orders)
        paid = sum(Decimal(str(o["paid_amount"])) for o in orders)
        self.stat_orders.set_value(str(len(orders)))
        self.stat_total.set_value(fmt.fmt_money(total))
        self.stat_balance.set_value(fmt.fmt_money(total - paid))
        rows = []
        for o in orders:
            date = o.get("created_at", "")[:10]
            t = fmt.fmt_money(o["total_amount"])
            p = fmt.fmt_money(o["paid_amount"])
            b = fmt.fmt_money(
                Decimal(str(o["total_amount"])) - Decimal(str(o["paid_amount"]))
            )
            rows.append([date, t, p, b])
        self.orders_table.set_rows(rows)

    def _new_supplier(self):
        dlg = SupplierDialog(self.api, self.store_id, parent=self)
        if dlg.exec():
            show_toast(self, strings.SUPPLIER_SAVED_TOAST)
            self.refresh()

    def _edit_supplier(self):
        row = self.supplier_list.currentRow()
        if row < 0:
            return
        supplier = self.supplier_list.item(row).data(Qt.ItemDataRole.UserRole)
        dlg = SupplierDialog(self.api, self.store_id, supplier=supplier, parent=self)
        if dlg.exec():
            show_toast(self, strings.SUPPLIER_SAVED_TOAST)
            self.refresh()
