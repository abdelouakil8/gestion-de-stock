"""Checkout screen — keyboard-first cashier flow, rebuilt for price levels."""

import tempfile
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import qtawesome as qta
import shiboken6
from loguru import logger
from PySide6.QtCore import QPoint, QSettings, QSize, Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from services.workers import run_api
from ui import format as fmt
from ui import strings
from ui.styles.tokens import ICON_SIZES, NEUTRAL, SPACING
from ui.widgets.customer_search import CustomerSearchBox
from ui.widgets.day_closing_dialog import DayClosingDialog
from ui.widgets.modal import ask_confirm, show_error
from ui.widgets.payment_dialogs import CheckoutPaymentDialog
from ui.widgets.pin_dialog import PinConfirmDialog
from ui.widgets.states import EmptyState
from ui.widgets.thumb import Thumb
from ui.widgets.toast import show_toast

from ._cart import (
    _CART_THUMB,
    _CELL_CONTROL_H,
    _PRICE_FIELDS,
    _RESULT_THUMB,
    CartLine,
    _centered_cell,
    _ResultRow,
)

_CLOSING_ORG = "GestionStockPOS"
_CLOSING_APP = "GestionStockPOS"


class CheckoutScreen(QWidget):
    def __init__(self, api, store_id: str, parent=None) -> None:
        super().__init__(parent)
        self.api = api
        self.store_id = store_id
        self.cart: list[CartLine] = []
        self.customer: dict | None = None
        self._parked_sales: list[dict] = []
        self._preferred_level: str | None = None
        self._promo: dict | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(*[SPACING["xl"]] * 4)
        layout.setSpacing(SPACING["md"])

        header = QHBoxLayout()
        title = QLabel(strings.CHECKOUT_TITLE)
        title.setObjectName("ScreenTitle")
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(QLabel(strings.CHECKOUT_CUSTOMER_LABEL))
        self.customer_label = QLabel(strings.CHECKOUT_CUSTOMER_ANONYMOUS)
        self.customer_label.setObjectName("Secondary")
        header.addWidget(self.customer_label)
        self.customer_search = CustomerSearchBox(
            self.api, self.store_id, self._on_customer_attached
        )
        self.customer_search.search.setFixedWidth(280)
        header.addWidget(self.customer_search)
        self.clear_customer_button = QPushButton(
            qta.icon("fa5s.times", color=NEUTRAL["600"]), ""
        )
        self.clear_customer_button.setObjectName("Ghost")
        self.clear_customer_button.setToolTip(strings.CUSTOMER_DETACH)
        self.clear_customer_button.clicked.connect(self._clear_customer)
        self.clear_customer_button.hide()
        header.addWidget(self.clear_customer_button)

        self.close_day_button = QPushButton(
            qta.icon("fa5s.cash-register", color=NEUTRAL["600"]),
            strings.CHECKOUT_CLOSE_DAY,
        )
        self.close_day_button.setObjectName("Secondary")
        self.close_day_button.setEnabled(False)
        self.close_day_button.clicked.connect(self._handle_close_day)
        header.addWidget(self.close_day_button)
        layout.addLayout(header)

        self.balance_warning = QLabel("")
        self.balance_warning.setObjectName("BalanceWarning")
        self.balance_warning.setWordWrap(True)
        self.balance_warning.hide()
        layout.addWidget(self.balance_warning)

        self.search = QLineEdit()
        self.search.setObjectName("SearchInput")
        self.search.setPlaceholderText(strings.CHECKOUT_SEARCH_PLACEHOLDER)
        self.search.textChanged.connect(self._on_search_text_changed)
        self.search.returnPressed.connect(self._on_enter)
        layout.addWidget(self.search)

        self._search_debounce = QTimer(self)
        self._search_debounce.setSingleShot(True)
        self._search_debounce.setInterval(250)
        self._search_debounce.timeout.connect(self._run_product_search)

        self.results = QListWidget()
        self.results.itemActivated.connect(self._on_result_chosen)
        self.results.hide()
        layout.addWidget(self.results)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            [
                strings.CHECKOUT_COL_PRODUCT,
                strings.CHECKOUT_COL_PACKAGING,
                strings.CHECKOUT_COL_LEVEL,
                strings.CHECKOUT_COL_UNIT_PRICE,
                strings.CHECKOUT_COL_QTY,
                strings.CHECKOUT_COL_DISCOUNT,
                strings.CHECKOUT_COL_TOTAL,
                strings.CHECKOUT_COL_REMOVE,
            ]
        )
        from PySide6.QtWidgets import QHeaderView

        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column, width in (
            (1, 112),
            (2, 138),
            (3, 124),
            (4, 112),
            (5, 100),
            (6, 112),
            (7, 44),
        ):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(column, width)
        for column in (3, 4, 5, 6):
            item = self.table.horizontalHeaderItem(column)
            if item is not None:
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(_CART_THUMB + 6)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)

        self.cart_stack = QStackedWidget()
        self.cart_empty = EmptyState(
            "fa5s.cash-register",
            strings.CHECKOUT_CART_EMPTY,
            strings.CHECKOUT_CART_EMPTY_HINT,
        )
        self.cart_stack.addWidget(self.cart_empty)
        self.cart_stack.addWidget(self.table)
        layout.addWidget(self.cart_stack, stretch=1)

        promo_row = QHBoxLayout()
        promo_caption = QLabel(strings.CHECKOUT_PROMO_LABEL)
        promo_caption.setObjectName("Caption")
        promo_row.addWidget(promo_caption)
        self.promo_input = QLineEdit()
        self.promo_input.setPlaceholderText(strings.CHECKOUT_PROMO_PLACEHOLDER)
        self.promo_input.setFixedWidth(180)
        self.promo_input.returnPressed.connect(self._apply_promo)
        promo_row.addWidget(self.promo_input)
        self.promo_apply = QPushButton(strings.CHECKOUT_PROMO_APPLY)
        self.promo_apply.setObjectName("Secondary")
        self.promo_apply.clicked.connect(self._apply_promo)
        promo_row.addWidget(self.promo_apply)
        self.promo_clear = QPushButton(qta.icon("fa5s.times", color=NEUTRAL["600"]), "")
        self.promo_clear.setObjectName("Ghost")
        self.promo_clear.setToolTip(strings.CHECKOUT_PROMO_REMOVE)
        self.promo_clear.clicked.connect(self._clear_promo)
        self.promo_clear.hide()
        promo_row.addWidget(self.promo_clear)
        self.promo_label = QLabel("")
        self.promo_label.setObjectName("Secondary")
        promo_row.addWidget(self.promo_label)
        promo_row.addStretch(1)
        layout.addLayout(promo_row)

        footer = QHBoxLayout()
        self.suspend_button = QPushButton(
            qta.icon("fa5s.pause", color=NEUTRAL["600"]), strings.CHECKOUT_SUSPEND
        )
        self.suspend_button.setObjectName("Secondary")
        self.suspend_button.setToolTip(strings.CHECKOUT_SUSPEND_TIP)
        self.suspend_button.clicked.connect(self._suspend_sale)
        footer.addWidget(self.suspend_button)
        self.resume_button = QPushButton(
            qta.icon("fa5s.play", color=NEUTRAL["600"]), strings.CHECKOUT_RESUME
        )
        self.resume_button.setObjectName("Secondary")
        self.resume_button.setToolTip(strings.CHECKOUT_RESUME_TIP)
        self.resume_button.clicked.connect(self._resume_sale)
        self.resume_button.setEnabled(False)
        footer.addWidget(self.resume_button)
        footer.addStretch(1)
        total_caption = QLabel(strings.CHECKOUT_TOTAL)
        total_caption.setObjectName("Caption")
        footer.addWidget(total_caption)
        self.total_label = QLabel(fmt.fmt_money(0))
        self.total_label.setObjectName("TotalAmount")
        footer.addWidget(self.total_label)
        footer.addSpacing(SPACING["xl"])
        self.pay_button = QPushButton(
            qta.icon("fa5s.hand-holding-usd", color="white"), strings.CHECKOUT_PAY
        )
        self.pay_button.setObjectName("Pay")
        self.pay_button.setIconSize(QSize(ICON_SIZES["lg"], ICON_SIZES["lg"]))
        self.pay_button.clicked.connect(self._checkout)
        self.pay_button.setEnabled(False)
        footer.addWidget(self.pay_button)
        layout.addLayout(footer)

        QShortcut(QKeySequence(Qt.Key.Key_F12), self, activated=self._checkout)
        QShortcut(QKeySequence(Qt.Key.Key_F9), self, activated=self._suspend_sale)
        QShortcut(QKeySequence(Qt.Key.Key_F10), self, activated=self._resume_sale)

        self._rebuild_table()
        self._refresh_close_button()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._refresh_close_button()

    # ------------------------------------------------------------ customer

    def _on_customer_attached(self, customer: dict) -> None:
        self.customer = customer
        self.customer_search.clear()
        self._refresh_customer_strip()
        self._apply_customer_pricing(customer)
        self._load_customer_balance(customer)
        self.search.setFocus()

    def _clear_customer(self) -> None:
        self.customer = None
        self._preferred_level = None
        self._hide_balance_warning()
        self._refresh_customer_strip()
        self.search.setFocus()

    def _apply_customer_pricing(self, customer: dict) -> None:
        level = customer.get("default_price_level")
        if not level or level not in _PRICE_FIELDS:
            self._preferred_level = None
            return
        self._preferred_level = level
        for line in self.cart:
            line.level = level
            line.manual_price = None
        if self.cart:
            self._rebuild_table()
        label = strings.PRICE_LEVEL_LABELS.get(level, level)
        show_toast(self, strings.CHECKOUT_PRICE_LEVEL_APPLIED.format(level=label))

    def _load_customer_balance(self, customer: dict) -> None:
        customer_id = customer["id"]
        run_api(
            lambda: self.api.stats_customer(customer_id),
            lambda stats, c=customer: self._on_customer_balance(c, stats),
            lambda err: self._hide_balance_warning(),
        )

    def _on_customer_balance(self, customer: dict, stats: object) -> None:
        if not shiboken6.isValid(self):
            return
        if self.customer is None or str(self.customer.get("id")) != str(
            customer.get("id")
        ):
            return
        try:
            balance = Decimal(str(stats.get("outstanding_balance", "0")))
        except (TypeError, ValueError, ArithmeticError):
            balance = Decimal("0")
        if balance > 0:
            self.balance_warning.setText(
                strings.CHECKOUT_BALANCE_WARNING.format(balance=fmt.fmt_money(balance))
            )
            self.balance_warning.show()
        else:
            self._hide_balance_warning()

    def _hide_balance_warning(self) -> None:
        self.balance_warning.hide()
        self.balance_warning.setText("")

    def _refresh_customer_strip(self) -> None:
        if self.customer:
            self.customer_label.setText(
                f"{self.customer['name']} · {self.customer['phone']}"
            )
            self.customer_label.setStyleSheet("font-weight: 600;")
            self.customer_search.hide()
            self.clear_customer_button.show()
        else:
            self.customer_label.setText(strings.CHECKOUT_CUSTOMER_ANONYMOUS)
            self.customer_label.setStyleSheet("")
            self.customer_search.show()
            self.clear_customer_button.hide()

    # ------------------------------------------------------------ products

    def _on_search_text_changed(self, text: str) -> None:
        if not text.strip():
            self._search_debounce.stop()
            self.results.clear()
            self.results.setFixedHeight(0)
            self.results.hide()
            return
        self._search_debounce.start()

    def _run_product_search(self) -> None:
        query = self.search.text().strip()
        if not query:
            self.results.hide()
            return
        run_api(
            lambda: self.api.search_products(
                self.store_id, query=query, limit=8, active_only=True
            ),
            lambda products, q=query: self._show_results(q, products),
            lambda err: show_error(self, err.message),
        )

    def _show_results(self, query: str, products: object) -> None:
        if not shiboken6.isValid(self):
            return
        if query != self.search.text().strip():
            return
        self.results.clear()
        matches = list(products or [])[:8]
        for product in matches:
            item = QListWidgetItem()
            row = _ResultRow(product)
            item.setSizeHint(row.sizeHint())
            item.setData(Qt.ItemDataRole.UserRole, product)
            self.results.addItem(item)
            self.results.setItemWidget(item, row)
        if matches:
            row_h = _RESULT_THUMB + SPACING["sm"] * 2
            visible = min(len(matches), 5)
            self.results.setFixedHeight(row_h * visible + 10)
        self.results.setVisible(bool(matches))

    def _shown_products(self) -> list[dict]:
        products = []
        for i in range(self.results.count()):
            data = self.results.item(i).data(Qt.ItemDataRole.UserRole)
            if data:
                products.append(data)
        return products

    # ------------------------------------------------------------- adding

    def _on_enter(self) -> None:
        query = self.search.text().strip()
        if not query:
            return
        for product in self._shown_products():
            if product.get("barcode") == query:
                self._add_to_cart(product)
                return
        run_api(
            lambda: self.api.get_product_by_barcode(self.store_id, query),
            self._add_to_cart,
            lambda err, q=query: self._on_barcode_miss(q),
        )

    def _on_barcode_miss(self, query: str) -> None:
        if self.results.count() > 0:
            self._on_result_chosen(self.results.item(0))
            return
        show_error(self, strings.CHECKOUT_NO_RESULT.format(query=query))

    def _on_result_chosen(self, item: QListWidgetItem) -> None:
        product = item.data(Qt.ItemDataRole.UserRole)
        if product:
            self._add_to_cart(product)

    def _add_to_cart(self, product: object) -> None:
        for line in self.cart:
            if line.product["id"] == product["id"]:
                line.quantity += 1
                self._rebuild_table()
                self._after_add()
                return
        line = CartLine(product)
        if self._preferred_level:
            line.level = self._preferred_level
        self.cart.append(line)
        self._rebuild_table()
        self._after_add()

    def _after_add(self) -> None:
        self.search.clear()
        self.results.clear()
        self.results.setFixedHeight(0)
        self.results.hide()
        self.search.setFocus()

    # --------------------------------------------------------------- cart

    def _rebuild_table(self) -> None:
        from PySide6.QtWidgets import QTableWidgetItem

        self.table.setRowCount(0)
        for index, line in enumerate(self.cart):
            row = self.table.rowCount()
            self.table.insertRow(row)

            product_cell = QWidget()
            cell_layout = QHBoxLayout(product_cell)
            cell_layout.setContentsMargins(SPACING["xs"], 2, SPACING["xs"], 2)
            cell_layout.setSpacing(SPACING["sm"])
            thumb = Thumb(_CART_THUMB)
            thumb.set_product(line.product)
            cell_layout.addWidget(thumb)
            name = QLabel(line.product["name"])
            name.setStyleSheet("font-weight: 600; background: transparent;")
            name.setToolTip(line.product["name"])
            cell_layout.addWidget(name, stretch=1)
            self.table.setCellWidget(row, 0, product_cell)

            packaging_combo = QComboBox()
            packaging_combo.addItem(strings.PACKAGING_UNIT, None)
            for packaging in line.product.get("packagings") or []:
                packaging_combo.addItem(
                    f"{packaging['label']} (×{packaging['unit_count']})", packaging
                )
            if line.packaging:
                for i in range(1, packaging_combo.count()):
                    data = packaging_combo.itemData(i)
                    if data and data.get("id") == line.packaging.get("id"):
                        packaging_combo.setCurrentIndex(i)
                        break
            packaging_combo.currentIndexChanged.connect(
                lambda _, target=line, combo=packaging_combo: (
                    self._on_packaging_changed(target, combo.currentData())
                )
            )
            packaging_combo.setFixedHeight(_CELL_CONTROL_H)
            self.table.setCellWidget(row, 1, _centered_cell(packaging_combo))

            level_combo = QComboBox()
            for value in ("detail", "gros", "super_gros"):
                level_combo.addItem(strings.PRICE_LEVEL_LABELS[value], value)
            level_combo.addItem(strings.PRICE_LEVEL_MANUAL, "manual")
            for i in range(level_combo.count()):
                if level_combo.itemData(i) == line.level:
                    level_combo.setCurrentIndex(i)
                    break
            level_combo.setFixedHeight(_CELL_CONTROL_H)
            level_combo.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
            )
            level_combo.currentIndexChanged.connect(
                lambda _, target=line, combo=level_combo: self._on_level_changed(
                    target, combo.currentData()
                )
            )
            self.table.setCellWidget(row, 2, _centered_cell(level_combo))

            price_spin = QDoubleSpinBox()
            price_spin.setDecimals(2)
            price_spin.setMaximum(99_999_999.99)
            price_spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
            price_spin.setFixedHeight(_CELL_CONTROL_H)
            price_spin.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
            )
            price_spin.setAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            price_spin.valueChanged.connect(
                lambda value, target=line: self._on_manual_price_changed(target, value)
            )
            line._price_spin = price_spin  # noqa: SLF001
            self.table.setCellWidget(row, 3, _centered_cell(price_spin))
            self._sync_price_cell(line)

            qty = QSpinBox()
            qty.setRange(1, 1_000_000)
            qty.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
            qty.setFixedHeight(_CELL_CONTROL_H)
            qty.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            qty.setAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            qty.setValue(line.quantity)
            qty.valueChanged.connect(
                lambda value, target=line: self._on_qty_changed(target, value)
            )
            self.table.setCellWidget(row, 4, _centered_cell(qty))

            discount_spin = QSpinBox()
            discount_spin.setRange(0, 99)
            discount_spin.setSuffix(" %")
            discount_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
            discount_spin.setFixedHeight(_CELL_CONTROL_H)
            discount_spin.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
            )
            discount_spin.setAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            discount_spin.setValue(int(line.discount_percent))
            discount_spin.setToolTip(strings.CHECKOUT_DISCOUNT_TIP)
            discount_spin.valueChanged.connect(
                lambda value, target=line: self._on_discount_changed(target, value)
            )
            self.table.setCellWidget(row, 5, _centered_cell(discount_spin))

            total_item = QTableWidgetItem(fmt.fmt_money(line.total))
            total_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            if line.packaging:
                total_item.setToolTip(
                    strings.CHECKOUT_BASE_UNITS.format(n=line.base_units)
                )
            self.table.setItem(row, 6, total_item)

            remove = QPushButton(qta.icon("fa5s.trash", color=NEUTRAL["500"]), "")
            remove.setObjectName("Ghost")
            remove.setToolTip(strings.CHECKOUT_REMOVE_LINE)
            remove.clicked.connect(lambda _, i=index: self._remove_line(i))
            self.table.setCellWidget(row, 7, remove)

        self._refresh_totals()
        self.cart_stack.setCurrentWidget(self.table if self.cart else self.cart_empty)

    def _refresh_totals(self) -> None:
        self.total_label.setText(fmt.fmt_money(self._cart_total()))
        self.pay_button.setEnabled(bool(self.cart))
        if self._promo is not None:
            discount = self._promo_discount_for(self._cart_subtotal())
            self.promo_label.setText(
                strings.CHECKOUT_PROMO_APPLIED.format(
                    code=self._promo.get("code", ""),
                    discount=fmt.fmt_money(discount),
                )
            )

    def _sync_price_cell(self, line: CartLine) -> None:
        spin = getattr(line, "_price_spin", None)
        if spin is None:
            return
        manual = line.level == "manual"
        spin.blockSignals(True)
        spin.setReadOnly(not manual)
        spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        spin.setValue(float(line.unit_price))
        spin.setToolTip(strings.CHECKOUT_MANUAL_PRICE_TIP if manual else "")
        spin.blockSignals(False)

    def _update_line_cells(self, line: CartLine) -> None:
        self._sync_price_cell(line)
        for row, cart_line in enumerate(self.cart):
            if cart_line is line:
                total_item = self.table.item(row, 6)
                if total_item is not None:
                    total_item.setText(fmt.fmt_money(line.total))
                    if line.packaging:
                        total_item.setToolTip(
                            strings.CHECKOUT_BASE_UNITS.format(n=line.base_units)
                        )
                    else:
                        total_item.setToolTip("")
        self._refresh_totals()

    def _on_packaging_changed(self, line: CartLine, packaging: object) -> None:
        line.packaging = packaging if isinstance(packaging, dict) else None
        line.manual_price = None
        self._update_line_cells(line)

    def _on_level_changed(self, line: CartLine, level: str) -> None:
        line.level = level
        if level == "manual" and line.manual_price is None:
            field = _PRICE_FIELDS["detail"]
            line.manual_price = Decimal(line._price_source()[field])
        elif level != "manual":
            line.manual_price = None
        self._update_line_cells(line)

    def _on_manual_price_changed(self, line: CartLine, value: float) -> None:
        if line.level == "manual":
            line.manual_price = Decimal(f"{value:.2f}")
            self._update_line_cells(line)

    def _on_qty_changed(self, line: CartLine, value: int) -> None:
        line.quantity = value
        self._update_line_cells(line)

    def _on_discount_changed(self, line: CartLine, value: int) -> None:
        line.discount_percent = int(value)
        self._update_line_cells(line)

    def _remove_line(self, index: int) -> None:
        del self.cart[index]
        self._rebuild_table()
        self.search.setFocus()

    # ------------------------------------------------------- park & recall

    def _suspend_sale(self) -> None:
        if not self.cart:
            show_toast(self, strings.CHECKOUT_SUSPEND_EMPTY, kind="warning")
            return
        self._park_current()
        show_toast(self, strings.CHECKOUT_SUSPENDED_TOAST)

    def _park_current(self) -> None:
        self._parked_sales.append(self._snapshot_cart())
        self.cart.clear()
        self.customer = None
        self._preferred_level = None
        self._clear_promo()
        self._hide_balance_warning()
        self._refresh_customer_strip()
        self._rebuild_table()
        self._update_resume_button()

    def _snapshot_cart(self) -> dict:
        return {
            "cart_items": [
                {
                    "product": line.product,
                    "packaging": line.packaging,
                    "quantity": line.quantity,
                    "level": line.level,
                    "manual_price": (
                        str(line.manual_price)
                        if line.manual_price is not None
                        else None
                    ),
                    "discount_percent": line.discount_percent,
                }
                for line in self.cart
            ],
            "customer": self.customer,
            "preferred_level": self._preferred_level,
            "parked_at": datetime.now().strftime("%H:%M"),
        }

    def _resume_sale(self) -> None:
        if not self._parked_sales:
            return
        if self.cart:
            if not ask_confirm(self, strings.CHECKOUT_RESUME_CONFIRM):
                return
            self._park_current()
        if len(self._parked_sales) == 1:
            self._restore_index(0)
        else:
            self._show_parked_menu()

    def _show_parked_menu(self) -> None:
        menu = QMenu(self)
        for index, snapshot in enumerate(self._parked_sales):
            customer = snapshot.get("customer")
            name = customer["name"] if customer else strings.CHECKOUT_CUSTOMER_ANONYMOUS
            label = strings.CHECKOUT_PARKED_ENTRY.format(
                time=snapshot.get("parked_at", ""),
                count=len(snapshot.get("cart_items", [])),
                customer=name,
            )
            action = menu.addAction(
                qta.icon("fa5s.receipt", color=NEUTRAL["600"]), label
            )
            action.triggered.connect(lambda _=False, i=index: self._restore_index(i))
        menu.exec(
            self.resume_button.mapToGlobal(QPoint(0, self.resume_button.height()))
        )

    def _restore_index(self, index: int) -> None:
        if not 0 <= index < len(self._parked_sales):
            return
        snapshot = self._parked_sales.pop(index)
        self._restore_parked(snapshot)

    def _restore_parked(self, snapshot: dict) -> None:
        self.cart = []
        for item in snapshot.get("cart_items", []):
            line = CartLine(item["product"])
            line.packaging = item.get("packaging")
            line.quantity = item.get("quantity", 1)
            line.level = item.get("level", "detail")
            manual = item.get("manual_price")
            line.manual_price = Decimal(manual) if manual is not None else None
            line.discount_percent = int(item.get("discount_percent", 0))
            self.cart.append(line)
        self.customer = snapshot.get("customer")
        self._preferred_level = snapshot.get("preferred_level")
        self._refresh_customer_strip()
        self._rebuild_table()
        self._update_resume_button()
        if self.customer:
            self._load_customer_balance(self.customer)
        else:
            self._hide_balance_warning()
        self.search.setFocus()

    def _update_resume_button(self) -> None:
        count = len(self._parked_sales)
        self.resume_button.setEnabled(count > 0)
        if count > 0:
            self.resume_button.setText(f"{strings.CHECKOUT_RESUME} ({count})")
        else:
            self.resume_button.setText(strings.CHECKOUT_RESUME)

    # ------------------------------------------------------------ checkout

    def _cart_subtotal(self) -> Decimal:
        return sum((line.total for line in self.cart), Decimal("0.00"))

    def _promo_discount_for(self, subtotal: Decimal) -> Decimal:
        if not self._promo:
            return Decimal("0.00")
        value = Decimal(str(self._promo.get("value", "0")))
        if self._promo.get("type") == "percent":
            raw = subtotal * value / 100
        else:
            raw = value
        return min(raw, subtotal).quantize(Decimal("0.01"))

    def _cart_total(self) -> Decimal:
        subtotal = self._cart_subtotal()
        return (subtotal - self._promo_discount_for(subtotal)).quantize(Decimal("0.01"))

    def _apply_promo(self) -> None:
        code = self.promo_input.text().strip()
        if not code:
            return
        subtotal = self._cart_subtotal()
        if subtotal <= 0:
            show_error(self, strings.CHECKOUT_PROMO_EMPTY_CART)
            return
        self.promo_apply.setEnabled(False)
        run_api(
            lambda: self.api.validate_promotion(self.store_id, code, f"{subtotal:.2f}"),
            self._on_promo_valid,
            self._on_promo_error,
        )

    def _on_promo_valid(self, result: object) -> None:
        if not shiboken6.isValid(self):
            return
        self._promo = dict(result)
        self.promo_input.setEnabled(False)
        self.promo_apply.setEnabled(False)
        self.promo_clear.show()
        self._refresh_totals()

    def _on_promo_error(self, err) -> None:
        if not shiboken6.isValid(self):
            return
        self.promo_apply.setEnabled(True)
        show_error(self, err.message)

    def _clear_promo(self) -> None:
        self._promo = None
        self.promo_input.clear()
        self.promo_input.setEnabled(True)
        self.promo_apply.setEnabled(True)
        self.promo_clear.hide()
        self.promo_label.clear()
        self._refresh_totals()

    def _line_payload(self, line: CartLine) -> dict:
        payload = {
            "product_id": line.product["id"],
            "quantity": line.quantity,
            "price_level": line.level if line.level != "manual" else "detail",
        }
        if line.packaging:
            payload["packaging_id"] = line.packaging["id"]
        if line.level == "manual" and line.manual_price is not None:
            payload["unit_price_override"] = f"{line.manual_price:.2f}"
        if line.discount_percent > 0:
            payload["discount_percent"] = int(line.discount_percent)
        return payload

    def _checkout(self) -> None:
        if not self.cart or not self.pay_button.isEnabled():
            return
        dialog = CheckoutPaymentDialog(
            self.api,
            self.store_id,
            self._cart_total(),
            customer=self.customer,
            parent=self,
        )
        if not dialog.exec() or dialog.payment is None:
            self.search.setFocus()
            return
        self.pay_button.setEnabled(False)
        items = [self._line_payload(line) for line in self.cart]
        payment = dialog.payment
        promo_code = self._promo.get("code") if self._promo else None
        run_api(
            lambda: self.api.checkout(
                self.store_id, items, payment, promo_code=promo_code
            ),
            lambda sale: self._on_sale_done(sale, payment),
            self._on_sale_error,
        )

    def _on_sale_done(self, sale: dict, payment: dict) -> None:
        customer_name = self.customer["name"] if self.customer else None
        self.cart.clear()
        self.customer = None
        self._preferred_level = None
        self._clear_promo()
        self._hide_balance_warning()
        self._refresh_customer_strip()
        self._rebuild_table()
        self.search.clear()
        self.results.clear()
        self.results.hide()
        window = self.window()
        if hasattr(window, "refresh_alerts_badge"):
            window.refresh_alerts_badge()
        self._refresh_close_button()
        self.search.setFocus()
        show_toast(self, strings.CHECKOUT_DONE_TOAST)
        run_api(
            lambda: self.api.get_receipt_pdf(sale["id"]),
            lambda pdf: self._print_receipt(sale, pdf, payment, customer_name),
            lambda err: show_error(self, err.message),
        )

    def _on_sale_error(self, err) -> None:
        self.pay_button.setEnabled(True)
        show_error(self, err.message)

    def _print_receipt(
        self, sale: dict, pdf: bytes, payment: dict, customer_name: str | None
    ) -> None:
        from services import escpos_printer, printing

        printer_name = printing.get_selected_printer()
        store_name = (
            self.window().store["name"]
            if hasattr(self.window(), "store")
            else "Boutique"
        )
        settings = (
            self.window().store.get("settings", {})
            if hasattr(self.window(), "store")
            else {}
        )

        if printer_name and escpos_printer.print_receipt_escpos(
            sale,
            printer_name,
            settings,
            store_name,
            customer_name,
            payment.get("payment_method", "cash"),
        ):
            return

        path = Path(tempfile.gettempdir()) / f"recu_{sale['id']}.pdf"
        try:
            path.write_bytes(pdf)
            printing.print_pdf(path, printer_name)
        except OSError as exc:
            logger.warning("Receipt print failed: {}", exc)
            show_error(self, strings.RECEIPT_PRINT_FAILED.format(path=path))

    # -------------------------------------------------- cloture de caisse

    def _closed_today(self) -> bool:
        settings = QSettings(_CLOSING_ORG, _CLOSING_APP)
        return settings.value(f"day_closed_{self.store_id}") == date.today().isoformat()

    def _refresh_close_button(self) -> None:
        if self._closed_today():
            self.close_day_button.setEnabled(False)
            self.close_day_button.setText(strings.CHECKOUT_CLOSE_DONE)
            return
        self.close_day_button.setText(strings.CHECKOUT_CLOSE_DAY)
        run_api(
            lambda: self.api.get_day_summary(self.store_id, date.today().isoformat()),
            self._on_close_summary,
            lambda err: None,
        )

    def _on_close_summary(self, summary: object) -> None:
        if not shiboken6.isValid(self) or self._closed_today():
            return
        self.close_day_button.setEnabled(int(summary.get("sales_count", 0)) > 0)

    def _handle_close_day(self) -> None:
        if self._closed_today():
            return
        pin_dialog = PinConfirmDialog(
            self.api, prompt=strings.CLOSING_PIN_PROMPT, parent=self
        )
        if not pin_dialog.exec() or not pin_dialog.pin:
            return
        pin = pin_dialog.pin
        today = date.today().isoformat()
        run_api(
            lambda: self.api.get_day_summary(self.store_id, today),
            lambda summary: self._open_closing(today, summary, pin),
            lambda err: show_error(self, err.message),
        )

    def _open_closing(self, today: str, summary: dict, pin: str) -> None:
        if not shiboken6.isValid(self):
            return
        if int(summary.get("sales_count", 0)) <= 0:
            show_error(self, strings.CLOSING_NO_SALES)
            return
        dialog = DayClosingDialog(
            self.api, self.store_id, today, summary, pin, parent=self
        )
        if dialog.exec() and dialog.result:
            QSettings(_CLOSING_ORG, _CLOSING_APP).setValue(
                f"day_closed_{self.store_id}", today
            )
            show_toast(self, strings.CLOSING_DONE_TOAST)
            self._refresh_close_button()
