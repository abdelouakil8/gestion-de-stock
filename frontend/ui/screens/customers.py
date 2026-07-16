"""Clients screen — list/search, per-customer analytics, sales history,
credit payments, loyal-customers ranking.

Left: searchable customer list. Right: the selected customer's panel
(contact + stat cards + sales history + unpaid sales with an inline
"Encaisser un paiement" action). When nothing is selected, the panel shows
the top-customers ranking so the screen is useful at a glance.
"""

from decimal import Decimal

import qtawesome as qta
from PySide6.QtCore import QDate, Qt, QTimer
from PySide6.QtWidgets import (
    QGridLayout,
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
from ui.styles.tokens import NEUTRAL, SPACING
from ui.widgets.badge import Badge
from ui.widgets.card import SectionCard, StatCard
from ui.widgets.customer_dialogs import CustomerFormDialog
from ui.widgets.data_table import DataTable
from ui.widgets.modal import show_error
from ui.widgets.pagination import PaginationBar
from ui.widgets.payment_dialogs import RecordPaymentDialog
from ui.widgets.states import EmptyState
from ui.widgets.toast import show_toast

_PAGE_SIZE = 50


class CustomersScreen(QWidget):
    def __init__(self, api, store_id: str, parent=None) -> None:
        super().__init__(parent)
        self.api = api
        self.store_id = store_id
        self.customers: list[dict] = []
        self.selected: dict | None = None
        self.customer_sales: list[dict] = []
        self._page = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(*[SPACING["xl"]] * 4)
        layout.setSpacing(SPACING["md"])

        header = QHBoxLayout()
        title = QLabel(strings.CUSTOMERS_TITLE)
        title.setObjectName("ScreenTitle")
        header.addWidget(title)
        header.addStretch(1)
        new_button = QPushButton(
            qta.icon("fa5s.user-plus", color="white"), strings.CUSTOMERS_NEW
        )
        new_button.setObjectName("Primary")
        new_button.clicked.connect(self._create_customer)
        header.addWidget(new_button)
        layout.addLayout(header)

        body = QHBoxLayout()
        body.setSpacing(SPACING["lg"])

        # ------------------------------------------------- left: the list
        left = QVBoxLayout()
        left.setSpacing(SPACING["sm"])
        self.search = QLineEdit()
        self.search.setObjectName("SearchInput")
        self.search.setPlaceholderText(strings.CUSTOMERS_SEARCH_PLACEHOLDER)
        # Debounced like every other live search (250 ms) — one API call per
        # pause, not one per keystroke.
        self._search_debounce = QTimer(self)
        self._search_debounce.setSingleShot(True)
        self._search_debounce.setInterval(250)
        self._search_debounce.timeout.connect(self._search_and_reset)
        self.search.textChanged.connect(lambda _: self._search_debounce.start())
        left.addWidget(self.search)

        self.list = QListWidget()
        self.list.currentItemChanged.connect(self._on_selected)
        left.addWidget(self.list, stretch=1)

        self.pagination = PaginationBar()
        self.pagination.page_changed.connect(self._on_customer_page)
        left.addWidget(self.pagination)

        left_holder = QWidget()
        left_holder.setLayout(left)
        left_holder.setMaximumWidth(340)
        body.addWidget(left_holder)

        # ------------------------------------------ right: details / top
        self.panel_stack = QStackedWidget()

        # Page 0 — top customers ranking (nothing selected).
        top_page = QVBoxLayout()
        top_card = SectionCard(strings.CUSTOMER_TOP_TITLE, "fa5s.crown")
        top_hint = QLabel(strings.CUSTOMER_TOP_HINT)
        top_hint.setObjectName("Muted")
        top_card.body.addWidget(top_hint)
        self.top_table = DataTable(
            [
                strings.CUSTOMER_NAME,
                strings.CUSTOMER_PHONE,
                strings.CUSTOMER_STAT_REVENUE,
                strings.CUSTOMER_STAT_SALES,
            ]
        )
        top_card.body.addWidget(self.top_table, stretch=1)
        top_page.addWidget(top_card, stretch=1)
        top_holder = QWidget()
        top_holder.setLayout(top_page)
        self.panel_stack.addWidget(top_holder)

        # Page 1 — selected customer detail.
        self.detail_holder = QWidget()
        detail = QVBoxLayout(self.detail_holder)
        detail.setSpacing(SPACING["md"])

        head = QHBoxLayout()
        self.detail_name = QLabel("")
        self.detail_name.setObjectName("ScreenTitle")
        head.addWidget(self.detail_name)
        self.detail_phone = QLabel("")
        self.detail_phone.setObjectName("Secondary")
        head.addWidget(self.detail_phone)
        head.addStretch(1)
        edit_button = QPushButton(
            qta.icon("fa5s.pen", color=NEUTRAL["600"]), strings.EDIT
        )
        edit_button.setObjectName("Ghost")
        edit_button.clicked.connect(self._edit_customer)
        head.addWidget(edit_button)
        detail.addLayout(head)

        self.detail_note = QLabel("")
        self.detail_note.setObjectName("Muted")
        self.detail_note.setWordWrap(True)
        detail.addWidget(self.detail_note)

        cards = QGridLayout()
        cards.setSpacing(SPACING["sm"])
        self.card_revenue = StatCard(
            strings.CUSTOMER_STAT_REVENUE, "fa5s.money-bill-wave"
        )
        self.card_profit = StatCard(strings.CUSTOMER_STAT_PROFIT, "fa5s.chart-line")
        self.card_sales = StatCard(strings.CUSTOMER_STAT_SALES, "fa5s.receipt")
        self.card_balance = StatCard(
            strings.CUSTOMER_STAT_BALANCE, "fa5s.hand-holding-usd"
        )
        self.card_last = StatCard(strings.CUSTOMER_STAT_LAST, "fa5s.history")
        for index, card in enumerate(
            [
                self.card_revenue,
                self.card_profit,
                self.card_sales,
                self.card_balance,
                self.card_last,
            ]
        ):
            cards.addWidget(card, index // 3, index % 3)
        detail.addLayout(cards)

        history_card = SectionCard(strings.CUSTOMER_SALES_HISTORY, "fa5s.history")
        pay_button = QPushButton(
            qta.icon("fa5s.hand-holding-usd", color="white"),
            strings.CUSTOMER_RECORD_PAYMENT,
        )
        pay_button.setObjectName("Primary")
        pay_button.clicked.connect(self._record_payment)
        history_card.header.addWidget(pay_button)
        self.sales_table = DataTable(
            [
                strings.CUSTOMER_COL_DATE,
                strings.CUSTOMER_COL_TOTAL,
                strings.CUSTOMER_COL_PAID,
                strings.CUSTOMER_COL_BALANCE,
                strings.CUSTOMER_COL_STATUS,
            ]
        )
        history_card.body.addWidget(self.sales_table, stretch=1)
        detail.addWidget(history_card, stretch=1)
        self.panel_stack.addWidget(self.detail_holder)

        # Page 2 — empty state (no customers at all).
        self.empty = EmptyState(
            "fa5s.users",
            strings.CUSTOMERS_EMPTY,
            strings.CUSTOMERS_EMPTY_HINT,
            strings.CUSTOMERS_NEW,
            self._create_customer,
        )
        self.panel_stack.addWidget(self.empty)

        body.addWidget(self.panel_stack, stretch=1)
        layout.addLayout(body, stretch=1)

    # ------------------------------------------------------------- loading

    def refresh(self) -> None:
        self.refresh_list()
        self._load_top_customers()

    def _search_and_reset(self) -> None:
        self._page = 0
        self.refresh_list()

    def refresh_list(self) -> None:
        query = self.search.text().strip() or None
        run_api(
            lambda: self.api.list_customers(self.store_id, query),
            self._on_customers,
            lambda err: show_error(self, err.message),
        )

    def _load_top_customers(self) -> None:
        today = QDate.currentDate()
        date_from = today.addYears(-1).toString("yyyy-MM-dd")
        date_to = today.toString("yyyy-MM-dd")
        run_api(
            lambda: self.api.stats_top_customers(
                self.store_id, date_from, date_to, limit=20
            ),
            self._on_top_customers,
            lambda err: None,
        )

    def _on_top_customers(self, top: object) -> None:
        self.top_table.set_rows(
            [
                [t["name"], t["phone"], fmt.fmt_money(t["revenue"]), t["sales_count"]]
                for t in top
            ]
        )

    def _on_customers(self, customers: object) -> None:
        self.customers = list(customers)
        self._display_customer_page()

    def _display_customer_page(self) -> None:
        total_pages = max(1, (len(self.customers) + _PAGE_SIZE - 1) // _PAGE_SIZE)
        self._page = min(self._page, total_pages - 1)
        start = self._page * _PAGE_SIZE
        page_items = self.customers[start : start + _PAGE_SIZE]

        selected_id = self.selected["id"] if self.selected else None
        self.list.blockSignals(True)
        self.list.clear()
        for customer in page_items:
            item = QListWidgetItem(f"{customer['name']}\n{customer['phone']}")
            item.setData(Qt.ItemDataRole.UserRole, customer)
            self.list.addItem(item)
            if customer["id"] == selected_id:
                self.list.setCurrentItem(item)
        self.list.blockSignals(False)

        self.pagination.set_state(self._page, total_pages)

        if not self.customers and not self.search.text().strip():
            self.panel_stack.setCurrentWidget(self.empty)
            self.selected = None
        elif self.selected is None:
            self.panel_stack.setCurrentIndex(0)

    def _on_customer_page(self, page: int) -> None:
        self._page = page
        self._display_customer_page()

    # ----------------------------------------------------------- selection

    def _on_selected(self, current: QListWidgetItem, _previous) -> None:
        if current is None:
            self.selected = None
            self.panel_stack.setCurrentIndex(0)
            return
        self.selected = current.data(Qt.ItemDataRole.UserRole)
        self.panel_stack.setCurrentWidget(self.detail_holder)
        self._render_contact()
        self._load_detail()

    def _render_contact(self) -> None:
        customer = self.selected
        self.detail_name.setText(customer["name"])
        self.detail_phone.setText(customer["phone"])
        self.detail_note.setText(customer.get("note") or "")
        self.detail_note.setVisible(bool(customer.get("note")))

    def _load_detail(self) -> None:
        customer_id = self.selected["id"]
        for card in (
            self.card_revenue,
            self.card_profit,
            self.card_sales,
            self.card_balance,
            self.card_last,
        ):
            card.set_value("…")
        run_api(
            lambda: self.api.stats_customer(customer_id),
            self._on_customer_stats,
            self._on_stats_error,
        )
        run_api(
            lambda: self.api.list_sales(self.store_id, customer_id=customer_id),
            self._on_sales,
            lambda err: show_error(self, err.message),
        )

    def _on_customer_stats(self, stats: object) -> None:
        if not self.selected or stats["customer_id"] != self.selected["id"]:
            return
        self.card_revenue.set_value(fmt.fmt_money(stats["total_revenue"]))
        self.card_profit.set_value(fmt.fmt_money(stats["total_profit"]))
        self.card_sales.set_value(str(stats["sales_count"]))
        balance = Decimal(str(stats["outstanding_balance"]))
        self.card_balance.set_value(
            fmt.fmt_money(balance), tone="danger" if balance > 0 else ""
        )
        last = stats.get("last_purchase_at")
        self.card_last.set_value(
            fmt.fmt_date(last) if last else strings.CUSTOMER_NEVER_PURCHASED
        )

    def _on_stats_error(self, err) -> None:
        if err.code in ("invalid_pin", "pin_not_configured"):
            for card in (self.card_revenue, self.card_profit):
                card.set_value("—")
            show_error(self, strings.STATS_PIN_REQUIRED)
        else:
            show_error(self, err.message)

    def _on_sales(self, sales: object) -> None:
        if not self.selected:
            return
        customer_id = self.selected["id"]
        self.customer_sales = [s for s in sales if s.get("customer_id") == customer_id]
        rows = []
        for sale in self.customer_sales:
            balance = Decimal(sale["total_amount"]) - Decimal(sale["paid_amount"])
            rows.append(
                [
                    fmt.fmt_datetime(sale.get("created_at")),
                    fmt.fmt_money(sale["total_amount"]),
                    fmt.fmt_money(sale["paid_amount"]),
                    fmt.fmt_money(balance),
                    "",  # status badge below
                ]
            )
        self.sales_table.set_rows(rows)
        for row, sale in enumerate(self.customer_sales):
            balance = Decimal(sale["total_amount"]) - Decimal(sale["paid_amount"])
            badge = (
                Badge(strings.CUSTOMER_SALE_CREDIT, "warning")
                if balance > 0
                else Badge(strings.CUSTOMER_SALE_PAID, "success")
            )
            holder = QWidget()
            holder_layout = QHBoxLayout(holder)
            holder_layout.setContentsMargins(4, 2, 4, 2)
            holder_layout.addWidget(badge)
            holder_layout.addStretch(1)
            self.sales_table.setCellWidget(row, 4, holder)

    # ------------------------------------------------------------- actions

    def _create_customer(self) -> None:
        dialog = CustomerFormDialog(self.api, self.store_id, parent=self)
        if dialog.exec() and dialog.result_customer:
            self.selected = dialog.result_customer
            self.refresh_list()

    def _edit_customer(self) -> None:
        if not self.selected:
            return
        dialog = CustomerFormDialog(
            self.api, self.store_id, customer=self.selected, parent=self
        )
        if dialog.exec() and dialog.result_customer:
            self.selected = dialog.result_customer
            self._render_contact()
            self.refresh_list()

    def _record_payment(self) -> None:
        unpaid = [
            s
            for s in self.customer_sales
            if Decimal(s["total_amount"]) > Decimal(s["paid_amount"])
        ]
        if not unpaid:
            show_error(self, strings.ALERTS_CREDITS_EMPTY)
            return
        # The selected row's sale when it is unpaid, else the oldest debt.
        row = self.sales_table.selected_row()
        sale = None
        if 0 <= row < len(self.customer_sales):
            candidate = self.customer_sales[row]
            if Decimal(candidate["total_amount"]) > Decimal(candidate["paid_amount"]):
                sale = candidate
        if sale is None:
            sale = min(unpaid, key=lambda s: s.get("created_at") or "")
        dialog = RecordPaymentDialog(self.api, sale, parent=self)
        if dialog.exec() and dialog.result_sale is not None:
            paid_now = dialog.amount_input.decimal()
            show_toast(
                self,
                strings.PAYMENT_RECORD_DONE.format(amount=fmt.fmt_money(paid_now)),
            )
            self._load_detail()
            window = self.window()
            if hasattr(window, "refresh_alerts_badge"):
                window.refresh_alerts_badge()
