"""Checkout screen — keyboard-first cashier flow, rebuilt for price levels.

Scan (keyboard-wedge) or type in the search box; Enter adds to the cart.
Each cart line carries a 3-state price-level selector (Détail / Gros /
Super gros): the UI shows the level's price from the product data for
instant feedback, but the SERVER resolves and enforces the real price at
checkout — the client never sends prices. F12 opens the payment dialog
(full / partial with customer), then prints the receipt.
"""

import tempfile
from decimal import Decimal
from pathlib import Path

import qtawesome as qta
import shiboken6
from loguru import logger
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
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
from ui.styles.tokens import ICON_SIZES, NEUTRAL, SPACING, THUMB_SIZES
from ui.widgets.badge import Badge
from ui.widgets.customer_search import CustomerSearchBox
from ui.widgets.modal import show_error
from ui.widgets.payment_dialogs import CheckoutPaymentDialog
from ui.widgets.states import EmptyState
from ui.widgets.thumb import Thumb
from ui.widgets.toast import show_toast

_PRICE_FIELDS = {
    "detail": "price_detail",
    "gros": "price_gros",
    "super_gros": "price_super_gros",
}

# One control height for every editable cell so a cart row reads as a single
# aligned band instead of a jumble of differently-sized widgets.
_CELL_CONTROL_H = 34
# A generous product thumbnail; the row hugs it (compact rows, big image).
_CART_THUMB = 44


def _centered_cell(widget: QWidget, left: int = 3, right: int = 3) -> QWidget:
    """Wrap a control so the table centers it vertically in the (taller) row
    instead of stretching it to the full cell height. A control with an
    Expanding horizontal policy also fills the cell width (auto-sizes to the
    column) instead of shrinking to its content."""
    holder = QWidget()
    layout = QHBoxLayout(holder)
    layout.setContentsMargins(left, 0, right, 0)
    layout.setSpacing(0)
    layout.addWidget(widget)
    return holder


class CartLine:
    def __init__(self, product: dict) -> None:
        self.product = product
        # None = the product's base unit ("Unité"); otherwise a packaging dict
        # with its own price triplet and unit_count.
        self.packaging: dict | None = None
        self.quantity = 1
        self.level = "detail"
        # Set only when the cashier types a price (level == "manual"); the
        # server re-checks it against the floor.
        self.manual_price: Decimal | None = None
        self.discount = Decimal("0.00")

    def _price_source(self) -> dict:
        return self.packaging if self.packaging else self.product

    @property
    def unit_price(self) -> Decimal:
        """Display-only mirror of the server rule: the resolved unit price."""
        if self.level == "manual" and self.manual_price is not None:
            return self.manual_price
        field = _PRICE_FIELDS.get(self.level, "price_detail")
        return Decimal(self._price_source()[field])

    @property
    def total(self) -> Decimal:
        gross = self.unit_price * self.quantity
        return (gross - self.discount).quantize(Decimal("0.01"))

    @property
    def base_units(self) -> int:
        """Stock units consumed = quantity × the packaging's unit_count."""
        unit_count = self.packaging["unit_count"] if self.packaging else 1
        return self.quantity * unit_count


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
        # Responsive: the product column absorbs all remaining width so the
        # cart ALWAYS fits the viewport — no horizontal scrolling on any
        # screen size or DPI scale (everything visible on one page).
        from PySide6.QtWidgets import QHeaderView

        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column, width in (
            (1, 112),  # Conditionnement ("Carton (×24)")
            (2, 138),  # Niveau de prix — a select (shows full "Super gros")
            (3, 124),  # Prix unitaire — enlarged
            (4, 112),  # Qté — enlarged, clean editable number field
            (5, 100),  # Remise
            (6, 112),  # Total
            (7, 44),  # remove
        ):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(column, width)
        # Every numeric header aligns right, matching its right-aligned values.
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
        # Same table language as every DataTable: no grid, alternating rows.
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
        if not shiboken6.isValid(self):
            return  # screen torn down while a search was in flight
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
            thumb = Thumb(_CART_THUMB)
            thumb.set_product(line.product)
            cell_layout.addWidget(thumb)
            name = QLabel(line.product["name"])
            name.setStyleSheet("font-weight: 600; background: transparent;")
            name.setToolTip(line.product["name"])  # full name if the cell clips
            cell_layout.addWidget(name, stretch=1)
            self.table.setCellWidget(row, 0, product_cell)

            # Conditionnement: "Unité" + one entry per packaging.
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

            # Price level as a clean select: Détail / Gros / Super gros /
            # Manuel. A dropdown shows the full label (no clipping) and stays
            # compact. Set the current index BEFORE connecting so seeding it
            # never fires the change handler.
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

            # Editable price cell — read-only for named levels, editable for
            # "Manuel" (the "type the price by hand" path). Server floor-checks.
            # Price: a clean number field (no spinner arrows — the price is
            # typed / resolved), read-only for named levels, editable in Manuel.
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
            line._price_spin = price_spin  # noqa: SLF001 (per-line cell handle)
            self.table.setCellWidget(row, 3, _centered_cell(price_spin))
            self._sync_price_cell(line)

            # Quantity: a clean editable number field (no cramped arrows) that
            # fills its column — the operator types any quantity and clearly
            # sees it. Consistent with the price/discount fields.
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

            # Discount: a typed number field (no arrows), fills the column.
            discount_spin = QDoubleSpinBox()
            discount_spin.setDecimals(2)
            discount_spin.setMaximum(99_999_999.99)
            discount_spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
            discount_spin.setFixedHeight(_CELL_CONTROL_H)
            discount_spin.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
            )
            discount_spin.setAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            discount_spin.setValue(float(line.discount))
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
        total = sum((line.total for line in self.cart), Decimal("0.00"))
        self.total_label.setText(fmt.fmt_money(total))
        self.pay_button.setEnabled(bool(self.cart))

    def _sync_price_cell(self, line: CartLine) -> None:
        """Set the price spin's value + editability from the line's state.

        Programmatic value changes are blocked so they never fire the manual
        handler. In manual mode the spin is editable; otherwise it displays
        the server-resolved price read-only.
        """
        spin = getattr(line, "_price_spin", None)
        if spin is None:
            return
        manual = line.level == "manual"
        spin.blockSignals(True)
        spin.setReadOnly(not manual)
        # No spinner arrows in either mode — a clean number field. In Manuel it
        # is editable (type the price); otherwise it shows the resolved price.
        spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        spin.setValue(float(line.unit_price))
        spin.setToolTip(strings.CHECKOUT_MANUAL_PRICE_TIP if manual else "")
        spin.blockSignals(False)

    def _update_line_cells(self, line: CartLine) -> None:
        """Refresh price/total cells in place (keeps widget focus)."""
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
        line.manual_price = None  # price source changed — drop any manual value
        self._update_line_cells(line)

    def _on_level_changed(self, line: CartLine, level: str) -> None:
        line.level = level
        if level == "manual" and line.manual_price is None:
            # Seed the manual price with the last resolved price so it is
            # immediately valid and the cashier just tweaks it.
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

    def _on_discount_changed(self, line: CartLine, value: float) -> None:
        line.discount = Decimal(f"{value:.2f}")
        self._update_line_cells(line)

    def _remove_line(self, index: int) -> None:
        del self.cart[index]
        self._rebuild_table()
        self.search.setFocus()

    # ------------------------------------------------------------ checkout

    def _cart_total(self) -> Decimal:
        return sum((line.total for line in self.cart), Decimal("0.00"))

    def _line_payload(self, line: CartLine) -> dict:
        """Server payload for one cart line — never a price, only a level and
        (optionally) a manual override and packaging id."""
        payload = {
            "product_id": line.product["id"],
            "quantity": line.quantity,
            # A manual line still needs a valid level enum server-side; the
            # override takes precedence over it for the actual price.
            "price_level": line.level if line.level != "manual" else "detail",
        }
        if line.packaging:
            payload["packaging_id"] = line.packaging["id"]
        if line.level == "manual" and line.manual_price is not None:
            payload["unit_price_override"] = f"{line.manual_price:.2f}"
        if line.discount > 0:
            payload["discount_amount"] = f"{line.discount:.2f}"
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
        run_api(
            lambda: self.api.checkout(self.store_id, items, payment),
            lambda sale: self._on_sale_done(sale, payment),
            self._on_sale_error,
        )

    def _on_sale_done(self, sale: dict, payment: dict) -> None:
        customer_name = self.customer["name"] if self.customer else None
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
            lambda pdf: self._print_receipt(sale, pdf, payment, customer_name),
            lambda err: show_error(self, err.message),
        )

    def _on_sale_error(self, err) -> None:
        self.pay_button.setEnabled(True)
        show_error(self, err.message)

    def _print_receipt(
        self, sale: dict, pdf: bytes, payment: dict, customer_name: str | None
    ) -> None:
        """Save the PDF and send it to the configured printer (Réglages)."""
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
            sale, printer_name, settings, store_name, customer_name, payment["method"]
        ):
            return

        path = Path(tempfile.gettempdir()) / f"recu_{sale['id']}.pdf"
        try:
            path.write_bytes(pdf)
            printing.print_pdf(path, printer_name)
        except OSError as exc:
            logger.warning("Receipt print failed: {}", exc)
            show_error(self, strings.RECEIPT_PRINT_FAILED.format(path=path))
