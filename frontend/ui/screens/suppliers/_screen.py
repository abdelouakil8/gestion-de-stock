"""Suppliers screen — supplier directory + global purchase-order view."""

from decimal import Decimal

import qtawesome as qta
from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from services.workers import run_api
from ui import format as fmt
from ui import strings
from ui.styles import tokens
from ui.styles.tokens import NEUTRAL, SPACING
from ui.widgets.card import SectionCard, StatCard
from ui.widgets.data_table import DataTable
from ui.widgets.modal import show_error
from ui.widgets.states import EmptyState, StatefulStack
from ui.widgets.toast import show_toast

from ._dialogs import (
    PurchaseOrderDetailsDialog,
    PurchaseOrderDialog,
    SupplierDialog,
    SupplierPaymentDialog,
    _money,
    _order_ref,
    _order_status,
)


def _configure_po_table(table: DataTable, status_col: int, actions_col: int) -> None:
    """Comfortable row height + fixed-width Statut/Actions columns."""
    table.verticalHeader().setDefaultSectionSize(46)
    header = table.horizontalHeader()
    header.setSectionResizeMode(status_col, QHeaderView.ResizeMode.Fixed)
    table.setColumnWidth(status_col, 104)
    header.setSectionResizeMode(actions_col, QHeaderView.ResizeMode.Fixed)
    table.setColumnWidth(actions_col, 200)


def _badge_cell(label: str, kind: str) -> QWidget:
    """Wrap a Badge in a centered cell holder for a DataTable."""
    from ui.widgets.badge import Badge

    holder = QWidget()
    layout = QHBoxLayout(holder)
    layout.setContentsMargins(SPACING["xs"], 2, SPACING["xs"], 2)
    layout.addWidget(Badge(label, kind))
    layout.addStretch(1)
    return holder


class SuppliersScreen(QWidget):
    def __init__(self, api, store_id, parent=None):
        super().__init__(parent)
        self.api = api
        self.store_id = store_id
        self._suppliers: list[dict] = []
        self._all_orders: list[dict] = []
        self._product_names: dict[str, str] = {}
        self._selected_supplier: dict | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(*[SPACING["xl"]] * 4)
        root.setSpacing(SPACING["md"])

        self.screen_tabs = QTabWidget()
        self.screen_tabs.addTab(
            self._build_suppliers_tab(), strings.PURCHASES_TAB_SUPPLIERS
        )
        self.screen_tabs.addTab(self._build_orders_tab(), strings.PURCHASES_TAB_ORDERS)
        root.addWidget(self.screen_tabs)

    # ------------------------------------------------------ Fournisseurs tab

    def _build_suppliers_tab(self) -> QWidget:
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
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
        return page

    def _build_detail(self):
        layout = QVBoxLayout(self.detail_content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACING["md"])

        self.detail_name = QLabel()
        self.detail_name.setObjectName("ScreenTitle")
        layout.addWidget(self.detail_name)

        stats_row = QHBoxLayout()
        self.stat_purchased = StatCard(strings.SUPPLIER_STAT_PURCHASED)
        self.stat_paid = StatCard(strings.SUPPLIER_STAT_PAID)
        self.stat_due = StatCard(strings.SUPPLIER_STAT_DUE)
        stats_row.addWidget(self.stat_purchased)
        stats_row.addWidget(self.stat_paid)
        stats_row.addWidget(self.stat_due)
        layout.addLayout(stats_row)

        self.detail_tabs = QTabWidget()

        # --- Informations tab
        info_page = QWidget()
        info_layout = QVBoxLayout(info_page)
        info_layout.setSpacing(SPACING["sm"])
        self.detail_phone = QLabel()
        self.detail_phone.setObjectName("Secondary")
        info_layout.addWidget(self.detail_phone)
        self.detail_note = QLabel()
        self.detail_note.setObjectName("Muted")
        self.detail_note.setWordWrap(True)
        info_layout.addWidget(self.detail_note)

        history_card = SectionCard(strings.SUPPLIER_ORDERS_HISTORY, "fa5s.boxes")
        self.orders_table = DataTable(
            [
                strings.SUPPLIER_COL_DATE,
                strings.SUPPLIER_COL_TOTAL,
                strings.SUPPLIER_COL_PAID,
                strings.SUPPLIER_COL_BALANCE,
            ]
        )
        self.orders_table.setMinimumHeight(180)
        history_card.body.addWidget(self.orders_table)
        info_layout.addWidget(history_card, stretch=1)

        info_btns = QHBoxLayout()
        info_btns.addStretch(1)
        edit_btn = QPushButton(strings.EDIT)
        edit_btn.setObjectName("Secondary")
        edit_btn.clicked.connect(self._edit_supplier)
        info_btns.addWidget(edit_btn)
        info_layout.addLayout(info_btns)
        self.detail_tabs.addTab(info_page, strings.SUPPLIER_TAB_INFO)

        # --- Bons de réception tab (this supplier's orders + actions)
        bons_page = QWidget()
        bons_layout = QVBoxLayout(bons_page)
        bons_layout.setSpacing(SPACING["sm"])
        bons_header = QHBoxLayout()
        bons_header.addStretch(1)
        new_order_btn = QPushButton(
            qta.icon("fa5s.plus", color="white"), strings.PO_NEW_ORDER
        )
        new_order_btn.setObjectName("Primary")
        new_order_btn.clicked.connect(self._new_order_for_selected)
        bons_header.addWidget(new_order_btn)
        bons_layout.addLayout(bons_header)
        self.detail_orders_table = DataTable(
            [
                strings.PO_GCOL_DATE,
                strings.PO_GCOL_REF,
                strings.PO_GCOL_TOTAL,
                strings.PO_GCOL_PAID,
                strings.PO_GCOL_BALANCE,
                strings.PO_GCOL_STATUS,
                strings.PO_GCOL_ACTIONS,
            ]
        )
        self.detail_orders_table.setMinimumHeight(220)
        _configure_po_table(self.detail_orders_table, status_col=5, actions_col=6)
        bons_layout.addWidget(self.detail_orders_table, stretch=1)
        self.detail_tabs.addTab(bons_page, strings.SUPPLIER_TAB_ORDERS)

        layout.addWidget(self.detail_tabs, stretch=1)

    # ---------------------------------------------------- Bons globaux tab

    def _build_orders_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACING["md"])

        header = QHBoxLayout()
        title = QLabel(strings.PURCHASES_TAB_ORDERS)
        title.setObjectName("ScreenTitle")
        header.addWidget(title)
        header.addStretch(1)
        new_btn = QPushButton(
            qta.icon("fa5s.plus", color="white"), strings.PO_NEW_ORDER
        )
        new_btn.setObjectName("Primary")
        new_btn.clicked.connect(lambda: self.open_new_purchase_order())
        header.addWidget(new_btn)
        layout.addLayout(header)

        # Filter bar.
        filters = QHBoxLayout()
        filters.setSpacing(SPACING["sm"])
        filters.addWidget(QLabel(strings.PO_FILTER_SUPPLIER))
        self.filter_supplier = QComboBox()
        self.filter_supplier.setMinimumWidth(180)
        filters.addWidget(self.filter_supplier)
        filters.addWidget(QLabel(strings.PO_FILTER_STATUS))
        self.filter_status = QComboBox()
        self.filter_status.addItem(strings.PO_STATUS_ALL, None)
        self.filter_status.addItem(strings.PO_STATUS_PAID, "paid")
        self.filter_status.addItem(strings.PO_STATUS_PARTIAL, "partial")
        self.filter_status.addItem(strings.PO_STATUS_UNPAID, "unpaid")
        filters.addWidget(self.filter_status)
        filters.addWidget(QLabel(strings.PO_FILTER_FROM))
        today = QDate.currentDate()
        self.filter_from = QDateEdit(QDate(today.year(), today.month(), 1))
        self.filter_from.setCalendarPopup(True)
        self.filter_from.setDisplayFormat("dd/MM/yyyy")
        filters.addWidget(self.filter_from)
        filters.addWidget(QLabel(strings.PO_FILTER_TO))
        self.filter_to = QDateEdit(today)
        self.filter_to.setCalendarPopup(True)
        self.filter_to.setDisplayFormat("dd/MM/yyyy")
        filters.addWidget(self.filter_to)
        apply_btn = QPushButton(
            qta.icon("fa5s.filter", color=NEUTRAL["600"]), strings.PO_FILTER_APPLY
        )
        apply_btn.clicked.connect(self._render_orders)
        filters.addWidget(apply_btn)
        filters.addStretch(1)
        layout.addLayout(filters)

        self.orders_global_table = DataTable(
            [
                strings.PO_GCOL_DATE,
                strings.PO_GCOL_SUPPLIER,
                strings.PO_GCOL_REF,
                strings.PO_GCOL_TOTAL,
                strings.PO_GCOL_PAID,
                strings.PO_GCOL_BALANCE,
                strings.PO_GCOL_STATUS,
                strings.PO_GCOL_ACTIONS,
            ]
        )
        _configure_po_table(self.orders_global_table, status_col=6, actions_col=7)
        self.orders_stack = StatefulStack(
            self.orders_global_table,
            EmptyState(
                "fa5s.file-invoice-dollar",
                strings.PO_ORDERS_EMPTY,
                strings.PO_ORDERS_EMPTY_HINT,
            ),
        )
        layout.addWidget(self.orders_stack, stretch=1)
        return page

    # -------------------------------------------------------------- loading

    def refresh(self):
        self.orders_stack.show_loading()
        run_api(
            lambda: self.api.list_suppliers(self.store_id),
            self._on_suppliers,
            lambda err: show_error(self, err.message),
        )
        run_api(
            lambda: self.api.list_products(self.store_id),
            self._on_products,
            lambda err: None,
        )
        run_api(
            lambda: self.api.list_purchase_orders(self.store_id),
            self._on_orders,
            lambda err: show_error(self, err.message),
        )

    def _on_suppliers(self, suppliers):
        self._suppliers = list(suppliers or [])
        self._filter()
        current = self.filter_supplier.currentData()
        self.filter_supplier.blockSignals(True)
        self.filter_supplier.clear()
        self.filter_supplier.addItem(strings.PO_FILTER_ALL_SUPPLIERS, None)
        for supplier in self._suppliers:
            self.filter_supplier.addItem(supplier["name"], str(supplier["id"]))
        index = self.filter_supplier.findData(current)
        self.filter_supplier.setCurrentIndex(index if index >= 0 else 0)
        self.filter_supplier.blockSignals(False)

    def _on_products(self, products_page: dict):
        items = products_page.get("items", []) if isinstance(products_page, dict) else []
        self._product_names = {str(p["id"]): p["name"] for p in items}

    def _on_orders(self, orders):
        self._all_orders = list(orders or [])
        self._render_orders()
        if self._selected_supplier is not None:
            self._render_supplier_orders(self._selected_supplier)

    def _supplier_name(self, supplier_id) -> str:
        for supplier in self._suppliers:
            if str(supplier["id"]) == str(supplier_id):
                return supplier["name"]
        return strings.PO_UNKNOWN_SUPPLIER

    # ------------------------------------------------------- global filters

    def _render_orders(self):
        supplier_id = self.filter_supplier.currentData()
        status = self.filter_status.currentData()
        date_from = self.filter_from.date().toString("yyyy-MM-dd")
        date_to = self.filter_to.date().toString("yyyy-MM-dd")

        rows_data = []
        for order in self._all_orders:
            if supplier_id and str(order.get("supplier_id")) != str(supplier_id):
                continue
            key, _label, _kind = _order_status(order)
            if status and key != status:
                continue
            created = str(order.get("created_at", ""))[:10]
            if created and not (date_from <= created <= date_to):
                continue
            rows_data.append(order)

        danger = QColor(tokens.SEMANTIC["danger"])
        self.orders_global_table.set_rows(
            [
                [
                    fmt.fmt_date(o.get("created_at")),
                    self._supplier_name(o.get("supplier_id")),
                    _order_ref(o),
                    fmt.fmt_money(o.get("total_amount")),
                    fmt.fmt_money(o.get("paid_amount")),
                    fmt.fmt_money(o.get("balance")),
                    "",
                    "",
                ]
                for o in rows_data
            ]
        )
        for row, order in enumerate(rows_data):
            key, label, kind = _order_status(order)
            balance = _money(order.get("balance"))
            if balance > 0:
                item = self.orders_global_table.item(row, 5)
                if item is not None:
                    item.setForeground(danger)
            self.orders_global_table.setCellWidget(row, 6, _badge_cell(label, kind))
            self.orders_global_table.setCellWidget(
                row, 7, self._actions_cell(order, on_reload=self._render_orders)
            )
        if rows_data:
            self.orders_stack.show_content()
        else:
            self.orders_stack.show_empty()

    def _actions_cell(self, order: dict, on_reload) -> QWidget:
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(SPACING["xs"], 2, SPACING["xs"], 2)
        row.setSpacing(SPACING["xs"])
        if _money(order.get("balance")) > 0:
            pay = QPushButton(strings.PO_ACTION_PAYMENT)
            pay.setObjectName("Secondary")
            pay.clicked.connect(lambda _=None, o=order: self._pay_order(o))
            row.addWidget(pay)
        details = QPushButton(strings.PO_ACTION_DETAILS)
        details.setObjectName("Ghost")
        details.clicked.connect(lambda _=None, o=order: self._show_order_details(o))
        row.addWidget(details)
        row.addStretch(1)
        return holder

    def _pay_order(self, order: dict):
        dialog = SupplierPaymentDialog(self.api, order, parent=self)
        if dialog.exec() and dialog.result_order is not None:
            show_toast(
                self,
                strings.PAYMENT_RECORD_DONE.format(
                    amount=fmt.fmt_money(
                        _money(dialog.result_order.get("paid_amount"))
                        - _money(order.get("paid_amount"))
                    )
                ),
            )
            self.refresh()

    def _show_order_details(self, order: dict):
        PurchaseOrderDetailsDialog(
            order,
            self._supplier_name(order.get("supplier_id")),
            self._product_names,
            parent=self,
        ).exec()

    # ------------------------------------------------------- supplier detail

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
            self._selected_supplier = None
            self.detail_stack.setCurrentWidget(self.detail_empty)

    def _on_select(self, row):
        if row < 0:
            self._selected_supplier = None
            self.detail_stack.setCurrentWidget(self.detail_empty)
            return
        item = self.supplier_list.item(row)
        supplier = item.data(Qt.ItemDataRole.UserRole)
        self._show_detail(supplier)

    def _show_detail(self, supplier):
        self._selected_supplier = supplier
        self.detail_name.setText(f"{supplier['name']}  ·  {supplier['phone']}")
        self.detail_phone.setText(supplier.get("phone", ""))
        self.detail_note.setText(supplier.get("note") or "—")
        self.detail_stack.setCurrentWidget(self.detail_content)
        self._render_supplier_orders(supplier)

    def _supplier_orders(self, supplier) -> list[dict]:
        sid = str(supplier["id"])
        return [o for o in self._all_orders if str(o.get("supplier_id")) == sid]

    def _render_supplier_orders(self, supplier):
        orders = self._supplier_orders(supplier)
        total = sum((_money(o.get("total_amount")) for o in orders), Decimal("0.00"))
        paid = sum((_money(o.get("paid_amount")) for o in orders), Decimal("0.00"))
        due = total - paid
        self.stat_purchased.set_value(fmt.fmt_money(total))
        self.stat_paid.set_value(fmt.fmt_money(paid))
        self.stat_due.set_value(fmt.fmt_money(due), "danger" if due > 0 else "")

        self.orders_table.set_rows(
            [
                [
                    fmt.fmt_date(o.get("created_at")),
                    fmt.fmt_money(o.get("total_amount")),
                    fmt.fmt_money(o.get("paid_amount")),
                    fmt.fmt_money(o.get("balance")),
                ]
                for o in orders
            ]
        )

        danger = QColor(tokens.SEMANTIC["danger"])
        self.detail_orders_table.set_rows(
            [
                [
                    fmt.fmt_date(o.get("created_at")),
                    _order_ref(o),
                    fmt.fmt_money(o.get("total_amount")),
                    fmt.fmt_money(o.get("paid_amount")),
                    fmt.fmt_money(o.get("balance")),
                    "",
                    "",
                ]
                for o in orders
            ]
        )
        for row, order in enumerate(orders):
            _key, label, kind = _order_status(order)
            if _money(order.get("balance")) > 0:
                item = self.detail_orders_table.item(row, 4)
                if item is not None:
                    item.setForeground(danger)
            self.detail_orders_table.setCellWidget(row, 5, _badge_cell(label, kind))
            self.detail_orders_table.setCellWidget(
                row, 6, self._detail_action_cell(order)
            )

    def _detail_action_cell(self, order: dict) -> QWidget:
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(SPACING["xs"], 2, SPACING["xs"], 2)
        if _money(order.get("balance")) > 0:
            pay = QPushButton(strings.PO_ACTION_PAYMENT)
            pay.setObjectName("Secondary")
            pay.clicked.connect(lambda _=None, o=order: self._pay_order(o))
            row.addWidget(pay)
        row.addStretch(1)
        return holder

    # ---------------------------------------------------------------- actions

    def _new_supplier(self):
        dlg = SupplierDialog(self.api, self.store_id, parent=self)
        if dlg.exec():
            show_toast(self, strings.SUPPLIER_SAVED_TOAST)
            self.refresh()

    def _edit_supplier(self):
        if self._selected_supplier is None:
            return
        dlg = SupplierDialog(
            self.api, self.store_id, supplier=self._selected_supplier, parent=self
        )
        if dlg.exec():
            show_toast(self, strings.SUPPLIER_SAVED_TOAST)
            self.refresh()

    def _new_order_for_selected(self):
        if self._selected_supplier is None:
            return
        dlg = PurchaseOrderDialog(
            self.api,
            self.store_id,
            self._suppliers,
            prefill_supplier_id=self._selected_supplier["id"],
            parent=self,
        )
        if dlg.exec():
            show_toast(self, strings.PO_CREATED_TOAST)
            self.refresh()

    def open_new_purchase_order(self, prefill_product: dict | None = None):
        """Open the new-order dialog (entry point for the Alertes screen)."""
        self.screen_tabs.setCurrentIndex(1)

        def _open(suppliers):
            self._suppliers = list(suppliers or [])
            dlg = PurchaseOrderDialog(
                self.api,
                self.store_id,
                self._suppliers,
                prefill_product=prefill_product,
                parent=self,
            )
            if dlg.exec():
                show_toast(self, strings.PO_CREATED_TOAST)
                self.refresh()

        run_api(
            lambda: self.api.list_suppliers(self.store_id),
            _open,
            lambda err: show_error(self, err.message),
        )
