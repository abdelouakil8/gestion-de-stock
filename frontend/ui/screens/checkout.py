"""Checkout screen — keyboard-first cashier flow, rebuilt for price levels.

Scan (keyboard-wedge) or type in the search box; Enter adds to the cart.
Each cart line carries a 3-state price-level selector (Détail / Gros /
Super gros): the UI shows the level's price from the product data for
instant feedback, but the SERVER resolves and enforces the real price at
checkout — the client never sends prices. F12 opens the payment dialog
(full / partial with customer), then prints the receipt.
"""

import os
import subprocess
import tempfile
from decimal import Decimal
from pathlib import Path

import qtawesome as qta
from loguru import logger
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from services.workers import run_api
from ui import format as fmt
from ui import strings
from ui.styles.tokens import ICON_SIZES, NEUTRAL, SPACING, THUMB_SIZES
from ui.widgets.badge import Badge
from ui.widgets.customer_search import CustomerSearchBox
from ui.widgets.modal import show_error
from ui.widgets.payment_dialogs import CheckoutPaymentDialog
from ui.widgets.segmented import PriceLevelSelector
from ui.widgets.states import EmptyState
from ui.widgets.thumb import Thumb
from ui.widgets.toast import show_toast

_PRICE_FIELDS = {
    "detail": "price_detail",
    "gros": "price_gros",
    "super_gros": "price_super_gros",
}


class CartLine:
    def __init__(self, product: dict) -> None:
        self.product = product
        self.quantity = 1
        self.level = "detail"

    @property
    def unit_price(self) -> Decimal:
        """Display-only mirror of the server rule: the level's price."""
        return Decimal(self.product[_PRICE_FIELDS[self.level]])

    @property
    def total(self) -> Decimal:
        return (self.unit_price * self.quantity).quantize(Decimal("0.01"))


class _ResultRow(QWidget):
    """Search result: thumbnail, name, stock badge, the three prices."""

    def __init__(self, product: dict) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(
            SPACING["xs"], SPACING["xs"], SPACING["xs"], SPACING["xs"]
        )
        layout.setSpacing(SPACING["md"])

        thumb = Thumb(THUMB_SIZES["list"])
        thumb.set_product(product)
        layout.addWidget(thumb)

        name = QLabel(product["name"])
        name.setStyleSheet("font-weight: 600; background: transparent;")
        layout.addWidget(name, stretch=1)

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
        layout.addWidget(stock_badge)

        prices = QLabel(
            f"{strings.PRICE_DETAIL} {fmt.fmt_money(product['price_detail'])}"
            f"  ·  {strings.PRICE_GROS} {fmt.fmt_money(product['price_gros'])}"
            f"  ·  {strings.PRICE_SUPER_GROS} "
            f"{fmt.fmt_money(product['price_super_gros'])}"
        )
        prices.setObjectName("Muted")
        layout.addWidget(prices)


class CheckoutScreen(QWidget):
    def __init__(self, api, store_id: str, parent=None) -> None:
        super().__init__(parent)
        self.api = api
        self.store_id = store_id
        self.cart: list[CartLine] = []
        self.customer: dict | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(*[SPACING["xl"]] * 4)
        layout.setSpacing(SPACING["md"])

        header = QHBoxLayout()
        title = QLabel(strings.CHECKOUT_TITLE)
        title.setObjectName("ScreenTitle")
        header.addWidget(title)
        header.addStretch(1)
        # Customer attachment strip (anonymous by default).
        header.addWidget(QLabel(strings.CHECKOUT_CUSTOMER_LABEL))
        self.customer_label = QLabel(strings.CHECKOUT_CUSTOMER_ANONYMOUS)
        self.customer_label.setObjectName("Secondary")
        header.addWidget(self.customer_label)
        # Inline search-and-attach box (replaces the picker dialog button).
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
        layout.addLayout(header)

        self.search = QLineEdit()
        self.search.setObjectName("SearchInput")
        self.search.setPlaceholderText(strings.CHECKOUT_SEARCH_PLACEHOLDER)
        self.search.textChanged.connect(self._on_search_text_changed)
        self.search.returnPressed.connect(self._on_enter)
        layout.addWidget(self.search)

        # Debounced live product search (250 ms); the Enter/barcode fast path
        # below is never debounced so the scanner stays instant.
        self._search_debounce = QTimer(self)
        self._search_debounce.setSingleShot(True)
        self._search_debounce.setInterval(250)
        self._search_debounce.timeout.connect(self._run_product_search)

        self.results = QListWidget()
        self.results.setMaximumHeight(212)
        self.results.itemActivated.connect(self._on_result_chosen)
        self.results.hide()
        layout.addWidget(self.results)

        # Cart: table page + designed empty page.
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            [
                strings.CHECKOUT_COL_PRODUCT,
                strings.CHECKOUT_COL_LEVEL,
                strings.CHECKOUT_COL_UNIT_PRICE,
                strings.CHECKOUT_COL_QTY,
                strings.CHECKOUT_COL_TOTAL,
                strings.CHECKOUT_COL_REMOVE,
            ]
        )
        self.table.horizontalHeader().setDefaultSectionSize(150)
        self.table.setColumnWidth(0, 300)
        self.table.setColumnWidth(1, 230)
        self.table.setColumnWidth(5, 48)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(THUMB_SIZES["cart"] + 12)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)

        self.cart_stack = QStackedWidget()
        self.cart_empty = EmptyState(
            "fa5s.cash-register",
            strings.CHECKOUT_CART_EMPTY,
            strings.CHECKOUT_CART_EMPTY_HINT,
        )
        self.cart_stack.addWidget(self.cart_empty)
        self.cart_stack.addWidget(self.table)
        layout.addWidget(self.cart_stack, stretch=1)

        footer = QHBoxLayout()
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
        self.pay_button.setEnabled(False)  # empty cart: visibly disabled
        footer.addWidget(self.pay_button)
        layout.addLayout(footer)

        QShortcut(QKeySequence(Qt.Key.Key_F12), self, activated=self._checkout)

        self._rebuild_table()

    # ------------------------------------------------------------ customer

    def _on_customer_attached(self, customer: dict) -> None:
        self.customer = customer
        self.customer_search.clear()
        self._refresh_customer_strip()
        self.search.setFocus()

    def _clear_customer(self) -> None:
        self.customer = None
        self._refresh_customer_strip()
        self.search.setFocus()

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
        """Debounce live search; empty text hides the results list."""
        if not text.strip():
            self._search_debounce.stop()
            self.results.clear()
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
        # A newer keystroke may have superseded this in-flight search.
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
        self.results.setVisible(bool(matches))

    def _shown_products(self) -> list[dict]:
        """Products currently rendered in the results list."""
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
        # 1) exact barcode among the currently shown results (fast path)
        for product in self._shown_products():
            if product.get("barcode") == query:
                self._add_to_cart(product)
                return
        # 2) authoritative barcode lookup (scanner path — never debounced)
        run_api(
            lambda: self.api.get_product_by_barcode(self.store_id, query),
            self._add_to_cart,
            lambda err, q=query: self._on_barcode_miss(q),
        )

    def _on_barcode_miss(self, query: str) -> None:
        # No exact barcode: fall back to the first visible search result.
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
        self.cart.append(CartLine(product))
        self._rebuild_table()
        self._after_add()

    def _after_add(self) -> None:
        self.search.clear()
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
            thumb = Thumb(THUMB_SIZES["cart"])
            thumb.set_product(line.product)
            cell_layout.addWidget(thumb)
            name = QLabel(line.product["name"])
            name.setStyleSheet("font-weight: 600; background: transparent;")
            cell_layout.addWidget(name, stretch=1)
            self.table.setCellWidget(row, 0, product_cell)

            selector = PriceLevelSelector(
                on_change=lambda level, target=line: self._on_level_changed(
                    target, level
                ),
                level=line.level,
            )
            selector_holder = QWidget()
            holder_layout = QHBoxLayout(selector_holder)
            holder_layout.setContentsMargins(SPACING["xs"], 0, SPACING["xs"], 0)
            holder_layout.addWidget(selector)
            holder_layout.addStretch(1)
            self.table.setCellWidget(row, 1, selector_holder)

            price_item = QTableWidgetItem(fmt.fmt_money(line.unit_price))
            price_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self.table.setItem(row, 2, price_item)

            qty = QSpinBox()
            qty.setRange(1, 1_000_000)
            qty.setValue(line.quantity)
            qty.valueChanged.connect(
                lambda value, target=line: self._on_qty_changed(target, value)
            )
            self.table.setCellWidget(row, 3, qty)

            total_item = QTableWidgetItem(fmt.fmt_money(line.total))
            total_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self.table.setItem(row, 4, total_item)

            remove = QPushButton(qta.icon("fa5s.trash", color=NEUTRAL["500"]), "")
            remove.setObjectName("Ghost")
            remove.setToolTip(strings.CHECKOUT_REMOVE_LINE)
            remove.clicked.connect(lambda _, i=index: self._remove_line(i))
            self.table.setCellWidget(row, 5, remove)

        self._refresh_totals()
        self.cart_stack.setCurrentWidget(self.table if self.cart else self.cart_empty)

    def _refresh_totals(self) -> None:
        total = sum((line.total for line in self.cart), Decimal("0.00"))
        self.total_label.setText(fmt.fmt_money(total))
        self.pay_button.setEnabled(bool(self.cart))

    def _update_line_cells(self, line: CartLine) -> None:
        """Refresh price/total cells in place (keeps widget focus)."""
        for row, cart_line in enumerate(self.cart):
            if cart_line is line:
                price_item = self.table.item(row, 2)
                total_item = self.table.item(row, 4)
                if price_item is not None:
                    price_item.setText(fmt.fmt_money(line.unit_price))
                if total_item is not None:
                    total_item.setText(fmt.fmt_money(line.total))
        self._refresh_totals()

    def _on_level_changed(self, line: CartLine, level: str) -> None:
        line.level = level
        self._update_line_cells(line)

    def _on_qty_changed(self, line: CartLine, value: int) -> None:
        line.quantity = value
        self._update_line_cells(line)

    def _remove_line(self, index: int) -> None:
        del self.cart[index]
        self._rebuild_table()
        self.search.setFocus()

    # ------------------------------------------------------------ checkout

    def _cart_total(self) -> Decimal:
        return sum((line.total for line in self.cart), Decimal("0.00"))

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
        items = [
            {
                "product_id": line.product["id"],
                "quantity": line.quantity,
                "price_level": line.level,
            }
            for line in self.cart
        ]
        payment = dialog.payment
        run_api(
            lambda: self.api.checkout(self.store_id, items, payment),
            self._on_sale_done,
            self._on_sale_error,
        )

    def _on_sale_done(self, sale: object) -> None:
        self.cart.clear()
        self.customer = None
        self._refresh_customer_strip()
        self._rebuild_table()
        # Stock changed: drop any stale search results (search is server-side).
        self.search.clear()
        self.results.clear()
        self.results.hide()
        window = self.window()
        if hasattr(window, "refresh_alerts_badge"):
            window.refresh_alerts_badge()  # a credit sale may add an alert
        self.search.setFocus()
        show_toast(self, strings.CHECKOUT_DONE_TOAST)
        run_api(
            lambda: self.api.get_receipt_pdf(sale["id"]),
            lambda pdf, sale_id=sale["id"]: self._print_receipt(sale_id, pdf),
            lambda err: show_error(self, err.message),
        )

    def _on_sale_error(self, err) -> None:
        self.pay_button.setEnabled(True)
        show_error(self, err.message)

    def _print_receipt(self, sale_id: str, pdf: object) -> None:
        """Save the PDF and hand it to the default printer via the shell."""
        path = Path(tempfile.gettempdir()) / f"recu_{sale_id}.pdf"
        try:
            path.write_bytes(pdf)
            if os.name == "nt":
                os.startfile(str(path), "print")  # default printer
            else:  # dev fallback on non-Windows
                subprocess.Popen(["xdg-open", str(path)])
        except OSError as exc:
            logger.warning("Receipt print failed: {}", exc)
            show_error(self, strings.RECEIPT_PRINT_FAILED.format(path=path))
