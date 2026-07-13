"""Inventory screen — product list, search, category rail, CRUD actions."""

from pathlib import Path

import qtawesome as qta
import shiboken6
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
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
from ui.styles.tokens import NEUTRAL, SPACING, THUMB_SIZES
from ui.widgets.badge import Badge
from ui.widgets.data_table import DataTable
from ui.widgets.modal import ModalDialog, ask_confirm, show_error
from ui.widgets.states import EmptyState
from ui.widgets.stock_adjust_dialog import StockAdjustDialog
from ui.widgets.stock_movements_view import StockMovementsView
from ui.widgets.thumb import Thumb
from ui.widgets.toast import show_toast

from ._detail import ProductDetailDialog
from ._form import ProductDialog


class InventoryScreen(QWidget):
    def __init__(self, api, store_id: str, parent=None) -> None:
        super().__init__(parent)
        self.api = api
        self.store_id = store_id
        self.products: list[dict] = []
        self.categories: list[dict] = []
        self.visible_products: list[dict] = []
        self._pending_focus: str | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(*[SPACING["xl"]] * 4)
        layout.setSpacing(SPACING["md"])

        header = QHBoxLayout()
        title = QLabel(strings.INVENTORY_TITLE)
        title.setObjectName("ScreenTitle")
        header.addWidget(title)
        hint = QLabel(strings.INVENTORY_DETAIL_HINT)
        hint.setObjectName("Muted")
        header.addWidget(hint)
        header.addStretch(1)
        layout.addLayout(header)

        toolbar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setObjectName("SearchInput")
        self.search.setPlaceholderText(strings.SEARCH)
        self.search.textChanged.connect(self._on_search_changed)
        toolbar.addWidget(self.search, stretch=1)

        new_button = QPushButton(
            qta.icon("fa5s.plus", color="white"), strings.INVENTORY_NEW_PRODUCT
        )
        new_button.setObjectName("Primary")
        new_button.clicked.connect(self._create_product)
        self.edit_button = QPushButton(
            qta.icon("fa5s.pen", color=NEUTRAL["600"]), strings.INVENTORY_EDIT_PRODUCT
        )
        self.edit_button.clicked.connect(self._edit_product)
        self.archive_button = QPushButton(strings.INVENTORY_ARCHIVE_PRODUCT)
        self.archive_button.setObjectName("Danger")
        self.archive_button.clicked.connect(self._archive_product)
        import_button = QPushButton(
            qta.icon("fa5s.file-upload", color=NEUTRAL["600"]),
            strings.IMPORT_BUTTON,
        )
        import_button.clicked.connect(self._import_csv)
        self.receive_button = QPushButton(
            qta.icon("fa5s.arrow-down", color=NEUTRAL["600"]), "Réceptionner"
        )
        self.receive_button.clicked.connect(self._receive_stock)
        self.adjust_button = QPushButton(
            qta.icon("fa5s.clipboard-check", color=NEUTRAL["600"]),
            strings.INVENTORY_ADJUST_BUTTON,
        )
        self.adjust_button.clicked.connect(self._adjust_stock)
        self.labels_button = QPushButton(
            qta.icon("fa5s.tag", color=NEUTRAL["600"]),
            strings.INVENTORY_LABELS_BUTTON,
        )
        self.labels_button.clicked.connect(self._open_label_printing)

        self.edit_button.setEnabled(False)
        self.archive_button.setEnabled(False)
        self.receive_button.setEnabled(False)
        for button in (
            new_button,
            import_button,
            self.adjust_button,
            self.labels_button,
            self.receive_button,
            self.edit_button,
            self.archive_button,
        ):
            toolbar.addWidget(button)

        self._search_debounce = QTimer(self)
        self._search_debounce.setSingleShot(True)
        self._search_debounce.setInterval(250)
        self._search_debounce.timeout.connect(self._run_search)
        self.search_results: list[dict] | None = None

        body = QHBoxLayout()
        body.setSpacing(SPACING["md"])
        self.category_rail = QListWidget()
        self.category_rail.setObjectName("CategoryRail")
        self.category_rail.setFixedWidth(200)
        self.category_rail.currentRowChanged.connect(lambda _: self._render())
        body.addWidget(self.category_rail)

        self.table = DataTable(
            [
                "",
                strings.INVENTORY_COL_NAME,
                strings.INVENTORY_COL_BARCODE,
                strings.INVENTORY_COL_CATEGORY,
                strings.INVENTORY_COL_STOCK,
                strings.INVENTORY_COL_DETAIL,
                strings.INVENTORY_COL_GROS,
                strings.INVENTORY_COL_SUPER_GROS,
                strings.INVENTORY_COL_ACTIVE,
            ]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Fixed
        )
        self.table.setColumnWidth(0, THUMB_SIZES["table"] + 14)
        self.table.verticalHeader().setDefaultSectionSize(THUMB_SIZES["table"] + 10)
        self.table.itemDoubleClicked.connect(lambda _: self._open_detail())
        self.table.itemSelectionChanged.connect(self._on_selection_changed)

        self.empty = EmptyState(
            "fa5s.box-open",
            strings.INVENTORY_EMPTY,
            strings.INVENTORY_EMPTY_HINT,
            strings.INVENTORY_NEW_PRODUCT,
            self._create_product,
        )
        self.stack = QStackedWidget()
        self.stack.addWidget(self.table)
        self.stack.addWidget(self.empty)
        body.addWidget(self.stack, stretch=1)

        products_page = QWidget()
        products_layout = QVBoxLayout(products_page)
        products_layout.setContentsMargins(0, 0, 0, 0)
        products_layout.setSpacing(SPACING["md"])
        products_layout.addLayout(toolbar)
        products_layout.addLayout(body, stretch=1)

        self.movements_view = StockMovementsView(self.api, self.store_id)
        self.tabs = QTabWidget()
        self.tabs.addTab(products_page, strings.INVENTORY_TAB_PRODUCTS)
        self.tabs.addTab(self.movements_view, strings.INVENTORY_TAB_MOVEMENTS)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self.tabs, stretch=1)

        self.refresh()

    def _on_tab_changed(self, index: int) -> None:
        if index == 1 and not self.movements_view._loaded_once:  # noqa: SLF001
            self.movements_view.refresh()

    def refresh(self) -> None:
        run_api(
            lambda: self.api.list_categories(self.store_id),
            self._on_categories,
            lambda err: show_error(self, err.message),
        )
        run_api(
            lambda: self.api.list_products(self.store_id),
            self._on_products,
            lambda err: show_error(self, err.message),
        )

    def focus_product(self, product_id: str) -> None:
        self._pending_focus = product_id
        self.search.clear()
        self.search_results = None
        if self.category_rail.count():
            self.category_rail.setCurrentRow(0)
        self.refresh()

    def _selected_category(self):
        item = self.category_rail.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def _on_categories(self, categories: object) -> None:
        self.categories = list(categories)
        current = self._selected_category()
        self.category_rail.blockSignals(True)
        self.category_rail.clear()
        all_item = QListWidgetItem(strings.INVENTORY_ALL_PRODUCTS)
        all_item.setData(Qt.ItemDataRole.UserRole, None)
        self.category_rail.addItem(all_item)
        for category in self.categories:
            item = QListWidgetItem(category["name"])
            item.setData(Qt.ItemDataRole.UserRole, category["id"])
            self.category_rail.addItem(item)
        uncat = QListWidgetItem(strings.INVENTORY_UNCATEGORIZED)
        uncat.setData(Qt.ItemDataRole.UserRole, "__uncategorized__")
        self.category_rail.addItem(uncat)
        target = 0
        for i in range(self.category_rail.count()):
            if self.category_rail.item(i).data(Qt.ItemDataRole.UserRole) == current:
                target = i
                break
        self.category_rail.setCurrentRow(target)
        self.category_rail.blockSignals(False)
        self._render()

    def _on_products(self, products: object) -> None:
        self.products = list(products)
        self._render()
        if self._pending_focus:
            for row, product in enumerate(self.visible_products):
                if product["id"] == self._pending_focus:
                    self.table.selectRow(row)
                    self.table.scrollToItem(self.table.item(row, 1))
                    break
            self._pending_focus = None

    def _on_search_changed(self, text: str) -> None:
        if not text.strip():
            self._search_debounce.stop()
            self.search_results = None
            self._render()
            return
        self._search_debounce.start()

    def _run_search(self) -> None:
        query = self.search.text().strip()
        if not query:
            self.search_results = None
            self._render()
            return
        run_api(
            lambda: self.api.search_products(self.store_id, query=query, limit=100),
            lambda results, q=query: self._on_search_results(q, results),
            lambda err: show_error(self, err.message),
        )

    def _on_search_results(self, query: str, results: object) -> None:
        if not shiboken6.isValid(self):
            return
        if query != self.search.text().strip():
            return
        self.search_results = list(results or [])
        self._render()

    def _render(self) -> None:
        category = self._selected_category()
        names = {c["id"]: c["name"] for c in self.categories}
        base = self.search_results if self.search_results is not None else self.products

        def in_category(product: dict) -> bool:
            if category is None:
                return True
            if category == "__uncategorized__":
                return not product.get("category_id")
            return product.get("category_id") == category

        self.visible_products = [p for p in base if in_category(p)]
        self.table.set_rows(
            [
                [
                    "",
                    p["name"],
                    p.get("barcode") or "—",
                    names.get(p.get("category_id"), "—"),
                    "",
                    fmt.fmt_money(p["price_detail"]),
                    fmt.fmt_money(p["price_gros"]),
                    fmt.fmt_money(p["price_super_gros"]),
                    strings.YES if p["is_active"] else strings.NO,
                ]
                for p in self.visible_products
            ]
        )
        for row, product in enumerate(self.visible_products):
            thumb = Thumb(THUMB_SIZES["table"])
            thumb.set_product(product)
            holder = QWidget()
            holder_layout = QHBoxLayout(holder)
            holder_layout.setContentsMargins(4, 2, 4, 2)
            holder_layout.addWidget(thumb, alignment=Qt.AlignmentFlag.AlignCenter)
            self.table.setCellWidget(row, 0, holder)

            stock_holder = QWidget()
            stock_layout = QHBoxLayout(stock_holder)
            stock_layout.setContentsMargins(4, 2, 4, 2)
            stock_layout.setSpacing(SPACING["xs"])
            stock_label = QLabel(str(product["stock_quantity"]))
            stock_layout.addWidget(stock_label)
            if product["stock_quantity"] <= product.get("low_stock_threshold", 5):
                stock_layout.addWidget(
                    Badge(strings.INVENTORY_LOW_STOCK_BADGE, "danger")
                )
            stock_layout.addStretch(1)
            self.table.setCellWidget(row, 4, stock_holder)

        empty = not self.visible_products and not self.products
        self.stack.setCurrentWidget(self.empty if empty else self.table)

    def _on_selection_changed(self) -> None:
        has_selection = 0 <= self.table.selected_row() < len(self.visible_products)
        self.edit_button.setEnabled(has_selection)
        self.archive_button.setEnabled(has_selection)
        self.receive_button.setEnabled(has_selection)

    def _selected_product(self) -> dict | None:
        row = self.table.selected_row()
        if row < 0 or row >= len(self.visible_products):
            show_error(self, strings.INVENTORY_SELECT_ROW_FIRST)
            return None
        return self.visible_products[row]

    def _create_product(self) -> None:
        dialog = ProductDialog(self.api, self.store_id, self.categories, parent=self)
        if dialog.exec():
            self.refresh()
            if dialog.result_product:
                show_toast(
                    self,
                    strings.PRODUCT_SAVED_TOAST.format(
                        name=dialog.result_product["name"]
                    ),
                )

    def _edit_product(self) -> None:
        product = self._selected_product()
        if not product:
            return
        run_api(
            lambda: self.api.get_product_details(product["id"]),
            lambda details: self._open_edit_dialog(details),
            lambda err: show_error(self, err.message),
        )

    def _open_edit_dialog(self, details: object) -> None:
        dialog = ProductDialog(
            self.api, self.store_id, self.categories, details=details, parent=self
        )
        if dialog.exec():
            self.refresh()
            if dialog.result_product:
                show_toast(
                    self,
                    strings.PRODUCT_SAVED_TOAST.format(
                        name=dialog.result_product["name"]
                    ),
                )

    def _open_detail(self) -> None:
        product = self._selected_product()
        if not product:
            return
        ProductDetailDialog(self.api, self.store_id, product, parent=self).exec()

    def _archive_product(self) -> None:
        product = self._selected_product()
        if not product:
            return
        if not ask_confirm(
            self, strings.INVENTORY_ARCHIVE_CONFIRM.format(name=product["name"])
        ):
            return
        run_api(
            lambda: self.api.archive_product(product["id"]),
            lambda _: self.refresh(),
            lambda err: show_error(self, err.message),
        )

    def _open_label_printing(self) -> None:
        window = self.window()
        target = getattr(window, "label_printing", None)
        if target is not None and hasattr(window, "navigate"):
            window.navigate(target)

    def _adjust_stock(self) -> None:
        dialog = StockAdjustDialog(self.api, self.store_id, parent=self)
        if not dialog.exec() or not dialog.result:
            return
        result = dialog.result
        self.refresh()
        if self.movements_view._loaded_once:  # noqa: SLF001
            self.movements_view.refresh()
        show_toast(
            self,
            strings.ADJUST_DONE_TOAST.format(
                product=result["name"],
                old=result["old_quantity"],
                new=result["new_quantity"],
            ),
        )

    def _receive_stock(self) -> None:
        product = self._selected_product()
        if not product:
            return
        qty, ok = QInputDialog.getInt(
            self,
            "Réceptionner",
            f"Quantité à ajouter pour {product['name']} :",
            1,
            1,
            1000000,
        )
        if ok and qty > 0:
            run_api(
                lambda: self.api.get_product_details(product["id"]),
                lambda details: self._do_receive_stock(details, qty),
                lambda err: show_error(self, err.message),
            )

    def _do_receive_stock(self, details: dict, added_qty: int) -> None:
        details["stock_quantity"] += added_qty
        run_api(
            lambda: self.api.update_product(details["id"], details),
            lambda _: self._on_receive_done(added_qty, details["name"]),
            lambda err: show_error(self, err.message),
        )

    def _on_receive_done(self, qty: int, name: str) -> None:
        self.refresh()
        show_toast(self, f"{qty} unités ajoutées à {name}.")

    def _import_csv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, strings.IMPORT_BUTTON, "", strings.IMPORT_FILE_FILTER
        )
        if not path:
            return
        data = Path(path).read_bytes()
        run_api(
            lambda: self.api.import_products_csv(self.store_id, data),
            self._on_import_done,
            lambda err: show_error(self, err.message),
        )

    def _on_import_done(self, result: object) -> None:
        created = result.get("created", 0)
        updated = result.get("updated", 0)
        errors = result.get("errors", [])
        show_toast(
            self,
            strings.IMPORT_DONE_TOAST.format(created=created, updated=updated),
        )
        if errors:
            dlg = ModalDialog(strings.IMPORT_DIALOG_TITLE, self)
            summary = QLabel(
                f"{strings.IMPORT_CREATED.format(count=created)}  ·  "
                f"{strings.IMPORT_UPDATED.format(count=updated)}  ·  "
                f"{strings.IMPORT_ERRORS.format(count=len(errors))}"
            )
            dlg.content.addWidget(summary)
            table = DataTable([strings.IMPORT_COL_ROW, strings.IMPORT_COL_ERROR])
            table.set_rows([[str(e["row"]), e["message"]] for e in errors])
            table.setMinimumHeight(200)
            dlg.content.addWidget(table)
            dlg.exec()
        self.refresh()
