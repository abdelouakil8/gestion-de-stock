"""Ventes — the sales journal.

A filterable list of every sale in the store: pick a date range and a sale
type, and the table shows date, customer (or an "Anonyme" chip for guest
sales), total / paid / balance and a paid-vs-credit status. Double-clicking a
row opens the sale detail dialog, which can reprint the receipt and — for a
sale with no customer yet — RESOLVE it: leave it anonymous, create a client
on the spot, or attach an existing one.

Date filtering is computed client-side from the local clock and passed to the
server (date_from / guest); the "Avec client" and "À crédit" refinements the
server does not model as flags are applied client-side on the fetched page.
All network goes through run_api; nothing here blocks the UI thread.
"""

import tempfile
from datetime import datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

import qtawesome as qta
from loguru import logger
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from services import printing
from services.workers import run_api
from ui import format as fmt
from ui import strings
from ui.styles.tokens import NEUTRAL, SPACING
from ui.widgets.badge import Badge
from ui.widgets.card import SectionCard
from ui.widgets.customer_dialogs import CustomerFormDialog
from ui.widgets.customer_search import CustomerSearchBox
from ui.widgets.data_table import DataTable
from ui.widgets.modal import ModalDialog, show_error
from ui.widgets.states import EmptyState, StatefulStack
from ui.widgets.toast import show_toast

_FETCH_LIMIT = 200

# Price-level -> French label, mirrors the checkout selector.
_LEVEL_LABELS = {
    "detail": strings.PRICE_DETAIL,
    "gros": strings.PRICE_GROS,
    "super_gros": strings.PRICE_SUPER_GROS,
}

# Date range keys -> (label, days back or None for "all").
_DATE_RANGES = [
    ("today", strings.SALES_FILTER_TODAY, 0),
    ("week", strings.SALES_FILTER_WEEK, 7),
    ("month", strings.SALES_FILTER_MONTH, 30),
    ("all", strings.SALES_FILTER_ALL, None),
]

# Type keys -> label. Mapping to server/client filtering lives in refresh().
_TYPES = [
    ("all", strings.SALES_TYPE_ALL),
    ("pending", strings.SALES_TYPE_GUEST_PENDING),
    ("confirmed", strings.SALES_TYPE_GUEST_CONFIRMED),
    ("with_customer", strings.SALES_TYPE_WITH_CUSTOMER),
    ("credit", strings.SALES_TYPE_CREDIT),
]


def _balance(sale: dict) -> Decimal:
    return Decimal(sale["total_amount"]) - Decimal(sale["paid_amount"])


class VentesScreen(QWidget):
    def __init__(self, api, store_id: str, on_view_product=None, parent=None) -> None:
        super().__init__(parent)
        self.api = api
        self.store_id = store_id
        self.on_view_product = on_view_product
        self.sales: list[dict] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(*[SPACING["xl"]] * 4)
        layout.setSpacing(SPACING["md"])

        header = QHBoxLayout()
        title = QLabel(strings.SALES_TITLE)
        title.setObjectName("ScreenTitle")
        header.addWidget(title)
        header.addStretch(1)
        refresh_button = QPushButton(
            qta.icon("fa5s.sync", color=NEUTRAL["600"]), strings.REFRESH
        )
        refresh_button.clicked.connect(self.refresh)
        header.addWidget(refresh_button)
        layout.addLayout(header)

        # --------------------------------------------------------- filters
        filters = QHBoxLayout()
        filters.setSpacing(SPACING["md"])

        self.range_combo = QComboBox()
        for key, label, _days in _DATE_RANGES:
            self.range_combo.addItem(label, key)
        self.range_combo.currentIndexChanged.connect(lambda _: self.refresh())
        filters.addWidget(self.range_combo)

        self.type_combo = QComboBox()
        for key, label in _TYPES:
            self.type_combo.addItem(label, key)
        self.type_combo.currentIndexChanged.connect(lambda _: self.refresh())
        filters.addWidget(self.type_combo)

        filters.addStretch(1)
        layout.addLayout(filters)

        # ----------------------------------------------------------- table
        self.table = DataTable(
            [
                strings.SALES_COL_DATE,
                strings.SALES_COL_CUSTOMER,
                strings.SALES_COL_TOTAL,
                strings.SALES_COL_PAID,
                strings.SALES_COL_BALANCE,
                strings.SALES_COL_STATUS,
            ]
        )
        self.table.itemDoubleClicked.connect(self._open_selected)
        self.stack = StatefulStack(
            self.table,
            EmptyState("fa5s.receipt", strings.SALES_EMPTY),
        )
        layout.addWidget(self.stack, stretch=1)

    # ------------------------------------------------------------- loading

    def _date_from(self) -> str | None:
        """ISO datetime for the selected range start, or None for 'Tout'."""
        key = self.range_combo.currentData()
        days = {k: d for k, _label, d in _DATE_RANGES}.get(key)
        if days is None:
            return None
        start_day = (datetime.now() - timedelta(days=days)).date()
        return datetime.combine(start_day, time.min).isoformat()

    def refresh(self) -> None:
        self.stack.show_loading()
        type_key = self.type_combo.currentData()
        guest = None
        if type_key == "pending":
            guest = "pending"
        elif type_key == "confirmed":
            guest = "confirmed"
        date_from = self._date_from()
        run_api(
            lambda: self.api.list_sales(
                self.store_id,
                guest=guest,
                date_from=date_from,
                limit=_FETCH_LIMIT,
            ),
            self._render,
            lambda err: self._on_error(err),
        )

    def _on_error(self, err) -> None:
        self.stack.show_empty()
        show_error(self, err.message)

    def _render(self, sales: object) -> None:
        rows = list(sales)
        # Client-side refinements the server does not model as flags.
        type_key = self.type_combo.currentData()
        if type_key == "with_customer":
            rows = [s for s in rows if s.get("customer_id")]
        elif type_key == "credit":
            rows = [s for s in rows if _balance(s) > 0]
        self.sales = rows

        if not rows:
            self.stack.show_empty()
            return

        self.table.set_rows(
            [
                [
                    fmt.fmt_datetime(sale.get("created_at")),
                    "",  # customer cell (widget below)
                    fmt.fmt_money(sale["total_amount"]),
                    fmt.fmt_money(sale["paid_amount"]),
                    fmt.fmt_money(_balance(sale)),
                    "",  # status badge below
                ]
                for sale in rows
            ]
        )
        for row, sale in enumerate(rows):
            self.table.setCellWidget(row, 1, self._customer_cell(sale))
            balance = _balance(sale)
            badge = (
                Badge(strings.SALES_STATUS_CREDIT, "warning")
                if balance > 0
                else Badge(strings.SALES_STATUS_PAID, "success")
            )
            self.table.setCellWidget(row, 5, self._chip_holder(badge))
        self.stack.show_content()

    @staticmethod
    def _chip_holder(widget: QWidget) -> QWidget:
        holder = QWidget()
        holder_layout = QHBoxLayout(holder)
        holder_layout.setContentsMargins(4, 2, 4, 2)
        holder_layout.addWidget(widget)
        holder_layout.addStretch(1)
        return holder

    def _customer_cell(self, sale: dict) -> QWidget:
        name = sale.get("customer_name")
        if name:
            label = QLabel(name)
            label.setStyleSheet("background: transparent;")
            return self._chip_holder(label)
        # No customer: a guest sale. Pending (never confirmed) vs confirmed.
        if sale.get("guest_confirmed_at"):
            badge = Badge(strings.SALES_GUEST_CONFIRMED_BADGE, "neutral")
        else:
            badge = Badge(strings.SALES_GUEST_PENDING_BADGE, "warning")
        return self._chip_holder(badge)

    # ------------------------------------------------------------- actions

    def _open_selected(self, _item) -> None:
        row = self.table.selected_row()
        if not (0 <= row < len(self.sales)):
            return
        sale = self.sales[row]
        dialog = SaleDetailDialog(self.api, self.store_id, sale, parent=self)
        dialog.exec()
        if dialog.changed:
            self.refresh()
            window = self.window()
            if hasattr(window, "refresh_alerts_badge"):
                window.refresh_alerts_badge()


class SaleDetailDialog(ModalDialog):
    """Read-only sale detail + receipt reprint + guest resolution.

    The resolution section (leave anonymous / create / attach a client) only
    appears when the sale has no customer yet. Any resolution sets
    ``self.changed`` so the caller refreshes the list and the alerts badge.
    """

    def __init__(self, api, store_id: str, sale: dict, parent=None) -> None:
        super().__init__(strings.SALE_DETAIL_TITLE, parent)
        self.api = api
        self.store_id = store_id
        self.sale = sale
        self.changed = False
        self._search_box: CustomerSearchBox | None = None

        # ------------------------------------------------------ summary
        head = QHBoxLayout()
        date_label = QLabel(fmt.fmt_datetime(sale.get("created_at")))
        date_label.setObjectName("Secondary")
        head.addWidget(date_label)
        head.addStretch(1)
        name = sale.get("customer_name")
        if name:
            who_text = name
            if sale.get("customer_phone"):
                who_text = f"{name} · {sale['customer_phone']}"
            who = QLabel(who_text)
            who.setStyleSheet("font-weight: 600; background: transparent;")
        else:
            who = Badge(strings.CUSTOMER_ANONYMOUS, "warning")
        head.addWidget(who)
        self.content.addLayout(head)

        # ------------------------------------------------------- items
        items_card = SectionCard(strings.CUSTOMER_SALES_HISTORY, "fa5s.receipt")
        items_table = DataTable(
            [
                strings.CHECKOUT_COL_LEVEL,
                strings.CHECKOUT_COL_QTY,
                strings.CHECKOUT_COL_UNIT_PRICE,
                strings.CHECKOUT_COL_TOTAL,
            ]
        )
        item_rows = []
        for item in sale.get("items", []):
            item_rows.append(
                [
                    _LEVEL_LABELS.get(item["price_level"], item["price_level"]),
                    str(item["quantity"]),
                    fmt.fmt_money(item["unit_price_applied"]),
                    fmt.fmt_money(item["line_total"]),
                ]
            )
        items_table.set_rows(item_rows)
        items_table.setMinimumHeight(160)
        items_card.body.addWidget(items_table)
        self.content.addWidget(items_card)

        # ------------------------------------------------------ totals
        totals = QVBoxLayout()
        totals.setSpacing(2)
        totals.addWidget(
            self._total_row(
                strings.PAYMENT_TOTAL_LABEL, fmt.fmt_money(sale["total_amount"])
            )
        )
        totals.addWidget(
            self._total_row(strings.SALES_COL_PAID, fmt.fmt_money(sale["paid_amount"]))
        )
        totals.addWidget(
            self._total_row(strings.SALES_COL_BALANCE, fmt.fmt_money(_balance(sale)))
        )
        self.content.addLayout(totals)

        # --------------------------------------------- resolution section
        if not sale.get("customer_id"):
            self._build_resolution_section()

        # -------------------------------------------------- footer buttons
        # The base dialog's OK/Cancel: relabel OK to "close", drop validation.
        self.ok_button.setText(strings.OK)
        reprint = QPushButton(
            qta.icon("fa5s.print", color=NEUTRAL["600"]), strings.SALE_REPRINT_RECEIPT
        )
        reprint.clicked.connect(self._reprint_receipt)
        self.buttons.addButton(reprint, self.buttons.ButtonRole.ActionRole)

        refund_btn = QPushButton(
            qta.icon("fa5s.undo", color=NEUTRAL["600"]), strings.REFUND_BUTTON
        )
        refund_btn.clicked.connect(self._open_refund)
        self.buttons.addButton(refund_btn, self.buttons.ButtonRole.ActionRole)

    # ------------------------------------------------------------ layout

    @staticmethod
    def _total_row(caption: str, value: str) -> QWidget:
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        caption_label = QLabel(caption)
        caption_label.setObjectName("Caption")
        row_layout.addWidget(caption_label)
        row_layout.addStretch(1)
        value_label = QLabel(value)
        value_label.setStyleSheet("font-weight: 700; background: transparent;")
        row_layout.addWidget(value_label)
        return row

    def _build_resolution_section(self) -> None:
        card = SectionCard(strings.SALE_RESOLVE_SECTION, "fa5s.user-tag")

        actions = QHBoxLayout()
        actions.setSpacing(SPACING["sm"])
        leave = QPushButton(
            qta.icon("fa5s.user-slash", color=NEUTRAL["600"]),
            strings.SALE_LEAVE_ANONYMOUS,
        )
        leave.clicked.connect(self._leave_anonymous)
        actions.addWidget(leave)
        create = QPushButton(
            qta.icon("fa5s.user-plus", color=NEUTRAL["600"]),
            strings.SALE_CREATE_CUSTOMER,
        )
        create.clicked.connect(self._create_customer)
        actions.addWidget(create)
        actions.addStretch(1)
        card.body.addLayout(actions)

        attach_label = QLabel(strings.SALE_ATTACH_CUSTOMER)
        attach_label.setObjectName("Caption")
        card.body.addWidget(attach_label)
        self._search_box = CustomerSearchBox(
            self.api, self.store_id, self._on_attach_picked
        )
        card.body.addWidget(self._search_box)

        self._resolution_buttons = [leave, create]
        self.content.addWidget(card)

    # ------------------------------------------------------------ resolve

    def _set_resolution_enabled(self, enabled: bool) -> None:
        for button in getattr(self, "_resolution_buttons", []):
            button.setEnabled(enabled)

    def _leave_anonymous(self) -> None:
        self._set_resolution_enabled(False)
        run_api(
            lambda: self.api.confirm_guest_sale(self.sale["id"]),
            lambda _sale: self._on_resolved(strings.SALE_LEFT_ANONYMOUS_DONE),
            self._on_resolve_error,
        )

    def _create_customer(self) -> None:
        dialog = CustomerFormDialog(self.api, self.store_id, parent=self)
        if dialog.exec() and dialog.result_customer:
            self._assign(dialog.result_customer["id"])

    def _on_attach_picked(self, customer: dict) -> None:
        self._assign(customer["id"])

    def _assign(self, customer_id: str) -> None:
        self._set_resolution_enabled(False)
        run_api(
            lambda: self.api.assign_sale_customer(self.sale["id"], customer_id),
            lambda _sale: self._on_resolved(strings.SALE_ASSIGNED_DONE),
            self._on_resolve_error,
        )

    def _on_resolved(self, message: str) -> None:
        self.changed = True
        show_toast(self, message)
        super().accept()

    def _on_resolve_error(self, err) -> None:
        self._set_resolution_enabled(True)
        if err.code in ("sale_customer_already_set", "sale_has_customer"):
            # State changed under us — report and refresh the caller's list.
            self.changed = True
            show_error(self, strings.SALE_ALREADY_HAS_CUSTOMER)
            super().accept()
            return
        show_error(self, err.message)

    # ------------------------------------------------------------ receipt

    def _reprint_receipt(self) -> None:
        run_api(
            lambda: self.api.get_receipt_pdf(self.sale["id"]),
            self._print_receipt,
            lambda err: show_error(self, err.message),
        )

    def _print_receipt(self, pdf: object) -> None:
        """Save the PDF and send it to the CONFIGURED printer (Réglages) —
        same path as CheckoutScreen so a reprint behaves identically."""
        path = Path(tempfile.gettempdir()) / f"recu_{self.sale['id']}.pdf"
        try:
            path.write_bytes(pdf)
            printing.print_pdf(path, printing.get_selected_printer())
        except OSError as exc:
            logger.warning("Receipt reprint failed: {}", exc)
            show_error(self, strings.RECEIPT_PRINT_FAILED.format(path=path))

    # ------------------------------------------------------------ refund

    def _open_refund(self) -> None:
        from ui.screens.refund_dialog import RefundDialog

        dialog = RefundDialog(self.api, self.sale, parent=self)
        if dialog.exec() and dialog.refund_created:
            self.changed = True
            show_toast(
                self,
                strings.REFUND_CREATED.format(
                    amount=fmt.fmt_money(dialog.refund_amount)
                ),
            )
