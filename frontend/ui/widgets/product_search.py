"""Shared product search + select widget.

ProductSearchBox is a QLineEdit with a frameless results popup below it — the
same live-search pattern as ui.widgets.customer_search.CustomerSearchBox, but
for products. It is a *pure search-and-select* control: it never stores the
selection itself, it just calls the host's ``on_select(product_dict)`` callback
when the operator picks a result. Used by the purchase-order dialog to pick a
product per order line.

Behaviour mirrors CustomerSearchBox:
- Typing is debounced (280 ms) and fires a smart product search off the UI
  thread via run_api(api.search_products(store_id, query, limit=8)).
- Results show "{name}" (with barcode when present) in a popup below the field.
- SELECT IS EXPLICIT: typing never selects. Only Enter / click on a highlighted
  result selects.
- Keyboard: Down/Up move the selection, Enter selects the highlighted row, Esc
  closes the popup.

All network goes through run_api; nothing here blocks the UI thread.
"""

from collections.abc import Callable

import shiboken6
from PySide6.QtCore import QEvent, QPoint, Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from services.workers import run_api
from ui import strings

_SEARCH_DEBOUNCE_MS = 280
_SEARCH_LIMIT = 8


class ProductSearchBox(QWidget):
    """Search products by name/barcode and select one.

    Args:
        api: the shared ApiClient (calls are wrapped in run_api).
        store_id: current store scope for the search.
        on_select: called with the selected product dict.
        placeholder: optional placeholder text for the field.
        parent: optional Qt parent.
    """

    def __init__(
        self,
        api,
        store_id: str,
        on_select: Callable[[dict], None],
        placeholder: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._api = api
        self._store_id = store_id
        self._on_select = on_select
        self._query = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.search = QLineEdit()
        self.search.setObjectName("SearchInput")
        self.search.setPlaceholderText(
            placeholder or strings.PO_LINE_PRODUCT_PLACEHOLDER
        )
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._on_text_changed)
        self.search.installEventFilter(self)
        layout.addWidget(self.search)

        # Frameless popup floating below the field (own top-level window so it
        # can overflow the host dialog without being clipped).
        self._popup = QFrame(self, Qt.WindowType.Popup)
        self._popup.setObjectName("CustomerSearchPopup")
        popup_layout = QVBoxLayout(self._popup)
        popup_layout.setContentsMargins(0, 0, 0, 0)
        self.results = QListWidget()
        self.results.setUniformItemSizes(True)
        self.results.itemClicked.connect(self._on_item_clicked)
        popup_layout.addWidget(self.results)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(_SEARCH_DEBOUNCE_MS)
        self._debounce.timeout.connect(self._run_search)

    # ------------------------------------------------------------ public API

    def clear(self) -> None:
        """Reset the field and hide the popup."""
        self._debounce.stop()
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self._query = ""
        self._hide_popup()

    def set_text(self, text: str) -> None:
        """Show a selected product's name without firing a new search."""
        self._debounce.stop()
        self.search.blockSignals(True)
        self.search.setText(text)
        self.search.blockSignals(False)
        self._query = ""
        self._hide_popup()

    # ------------------------------------------------------------ search flow

    def _on_text_changed(self, text: str) -> None:
        self._query = text.strip()
        if not self._query:
            self._debounce.stop()
            self._hide_popup()
            return
        self._debounce.start()  # restart on every keystroke

    def _run_search(self) -> None:
        query = self._query
        if not query:
            self._hide_popup()
            return
        run_api(
            lambda: self._api.search_products(
                self._store_id, query=query, limit=_SEARCH_LIMIT
            ),
            lambda products: self._on_results(query, products),
            self._on_error,
        )

    def _on_results(self, query: str, products: object) -> None:
        # The widget/popup may have been torn down while the search was in
        # flight (dialog closed) — touching deleted C++ objects would crash.
        if not shiboken6.isValid(self):
            return
        if query != self._query:  # superseded by a newer keystroke
            return
        self.results.clear()
        for product in products or []:
            barcode = product.get("barcode")
            label = f"{product['name']}   ·   {barcode}" if barcode else product["name"]
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, product)
            self.results.addItem(item)
        if not self.results.count():
            self._hide_popup()
            return
        self.results.setCurrentRow(0)
        self._show_popup()

    def _on_error(self, err) -> None:
        if not shiboken6.isValid(self):
            return
        self._hide_popup()

    # ------------------------------------------------------------ selection

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        self._activate(item)

    def _activate(self, item: QListWidgetItem | None) -> None:
        if item is None:
            return
        product = item.data(Qt.ItemDataRole.UserRole)
        if product:
            self._hide_popup()
            self._on_select(product)

    # ------------------------------------------------------------ popup mgmt

    def _show_popup(self) -> None:
        below = self.search.mapToGlobal(QPoint(0, self.search.height() + 2))
        self._popup.setFixedWidth(self.search.width())
        self._popup.move(below)
        rows = min(self.results.count(), 6)
        row_h = self.results.sizeHintForRow(0) if self.results.count() else 34
        self._popup.setFixedHeight(max(1, rows) * row_h + 8)
        self._popup.show()

    def _hide_popup(self) -> None:
        self._popup.hide()

    # ------------------------------------------------------------ key events

    def eventFilter(self, obj, event) -> bool:
        if obj is self.search and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                if not self._popup.isVisible():
                    if self.results.count():
                        self._show_popup()
                    return True
                self._move_selection(1 if key == Qt.Key.Key_Down else -1)
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if self._popup.isVisible() and self.results.count():
                    self._activate(self.results.currentItem())
                    return True
            if key == Qt.Key.Key_Escape:
                if self._popup.isVisible():
                    self._hide_popup()
                    return True
        return super().eventFilter(obj, event)

    def _move_selection(self, delta: int) -> None:
        count = self.results.count()
        if not count:
            return
        row = self.results.currentRow()
        row = (row + delta) % count
        self.results.setCurrentRow(row)
