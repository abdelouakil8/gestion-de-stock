"""Achats & Fournisseurs — suppliers directory + global purchase-order view.

Screen-level tabs:
- "Fournisseurs": the classic list + detail split panel. The detail panel
  carries three StatCards (Total acheté / Total payé / Reste dû) and its own
  Informations / Bons de réception tabs.
- "Bons de réception": a filterable global view of every purchase order, with
  inline "Paiement" / "Détails" actions and a "Nouveau bon" entry point.

All data flows through the local HTTP API via run_api (never the DB directly).
Purchase orders are loaded once per screen visit and filtered client-side, so
changing a filter costs no network round-trip.
"""

from decimal import Decimal

import qtawesome as qta
from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSpinBox,
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
from ui.widgets.modal import ModalDialog, show_error
from ui.widgets.product_search import ProductSearchBox
from ui.widgets.states import EmptyState, StatefulStack
from ui.widgets.toast import show_toast


def _money(value) -> Decimal:
    return Decimal(str(value)) if value is not None else Decimal("0.00")


def _order_status(order: dict) -> tuple[str, str, str]:
    """(filter_key, badge_label, badge_kind) for a purchase order.

    Green "Payé" when nothing is due, red "Impayé" when nothing is paid,
    amber "Partiel" in between."""
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


def _configure_po_table(table: DataTable, status_col: int, actions_col: int) -> None:
    """Comfortable row height + fixed-width Statut/Actions columns so the badge
    and inline buttons (Paiement / Détails) never clip or overlap."""
    table.verticalHeader().setDefaultSectionSize(46)
    header = table.horizontalHeader()
    header.setSectionResizeMode(status_col, QHeaderView.ResizeMode.Fixed)
    table.setColumnWidth(status_col, 104)
    header.setSectionResizeMode(actions_col, QHeaderView.ResizeMode.Fixed)
    table.setColumnWidth(actions_col, 200)


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
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
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
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.qty.valueChanged.connect(lambda _=None: self._recompute())
        layout.addWidget(self.qty)

        self.unit_cost = QDoubleSpinBox()
        self.unit_cost.setDecimals(2)
        self.unit_cost.setRange(0.0, 9_999_999.99)
        self.unit_cost.setFixedWidth(120)
        self.unit_cost.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.unit_cost.valueChanged.connect(lambda _=None: self._recompute())
        layout.addWidget(self.unit_cost)

        self.total_label = QLabel(fmt.fmt_money(0))
        self.total_label.setFixedWidth(120)
        self.total_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
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
        # Best-effort: prefill the unit cost from the product's stored cost
        # (owner data). The operator can override with the real supplier price.
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

        # Supplier selector.
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

        # Order-lines section header.
        lines_title = QLabel(strings.PO_LINES_SECTION)
        lines_title.setObjectName("SectionTitle")
        self.content.addWidget(lines_title)

        # Scrollable list of line rows.
        self._rows_holder = QWidget()
        self._rows_box = QVBoxLayout(self._rows_holder)
        self._rows_box.setContentsMargins(0, 0, 0, 0)
        self._rows_box.setSpacing(SPACING["xs"])
        # Trailing stretch keeps rows pinned to the top of the scroll area
        # instead of floating in the middle when there are only one or two.
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

        # Total footer.
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

        # Seed with one line (prefilled when arriving from the Alertes screen).
        first = self._add_row()
        if prefill_product is not None:
            first.set_product(prefill_product)

    def _add_row(self) -> _POLineRow:
        row = _POLineRow(self.api, self.store_id, self._remove_row, self._refresh_total)
        self._rows.append(row)
        # Insert before the trailing stretch so rows stay top-aligned.
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
        # Repopulate the global filter combo (Tous + each supplier).
        current = self.filter_supplier.currentData()
        self.filter_supplier.blockSignals(True)
        self.filter_supplier.clear()
        self.filter_supplier.addItem(strings.PO_FILTER_ALL_SUPPLIERS, None)
        for supplier in self._suppliers:
            self.filter_supplier.addItem(supplier["name"], str(supplier["id"]))
        index = self.filter_supplier.findData(current)
        self.filter_supplier.setCurrentIndex(index if index >= 0 else 0)
        self.filter_supplier.blockSignals(False)

    def _on_products(self, products):
        self._product_names = {str(p["id"]): p["name"] for p in (products or [])}

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

        # Informations tab: simple history table.
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

        # Bons tab: richer table with status + payment action.
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
        """Open the new-order dialog (entry point for the Alertes screen).

        Fetches suppliers fresh so the combo is always populated, then opens
        the dialog on the Bons de réception tab."""
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


def _badge_cell(label: str, kind: str) -> QWidget:
    """Wrap a Badge in a centered cell holder for a DataTable."""
    from ui.widgets.badge import Badge

    holder = QWidget()
    layout = QHBoxLayout(holder)
    layout.setContentsMargins(SPACING["xs"], 2, SPACING["xs"], 2)
    layout.addWidget(Badge(label, kind))
    layout.addStretch(1)
    return holder
