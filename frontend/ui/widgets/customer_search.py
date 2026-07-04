"""Shared customer search + attach widget.

CustomerSearchBox is a QLineEdit with a frameless results popup below it,
used verbatim by the Caisse header, the payment dialog (partial/credit
mode), and the Ventes sale-detail dialog. It is a *pure search-and-attach*
control: it never stores attachment state itself — it just calls the host's
``on_attach(customer_dict)`` callback when the operator picks or creates a
customer. The host screen owns "who is currently attached".

Behaviour:
- Typing is debounced (280 ms) and fires a smart customer search off the UI
  thread via run_api(api.list_customers(store_id, query, limit=8)).
- Results are shown as "{name} · {phone}" rows in a popup below the field.
- ATTACH IS EXPLICIT: typing never attaches. Only Enter / click on a
  highlighted result, or the "Créer « … »" action, attaches.
- Keyboard: Down/Up move the selection, Enter attaches the highlighted row
  (or triggers create when that row is highlighted), Esc closes the popup.
- When a non-empty query has no matches, a single actionable row
  "Créer « {query} »…" opens CustomerFormDialog prefilled with the typed
  text; on success the created customer is attached.

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
from ui.widgets.customer_dialogs import CustomerFormDialog

_SEARCH_DEBOUNCE_MS = 280
_SEARCH_LIMIT = 8
# Marks the synthetic "Créer « … »" row so we can tell it from a real result.
_CREATE_ROLE = Qt.ItemDataRole.UserRole + 1


class CustomerSearchBox(QWidget):
    """Search customers by name/phone and attach one (or create inline).

    Args:
        api: the shared ApiClient (calls are wrapped in run_api).
        store_id: current store scope for the search.
        on_attach: called with the selected/created customer dict.
        parent: optional Qt parent.
    """

    def __init__(
        self,
        api,
        store_id: str,
        on_attach: Callable[[dict], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._api = api
        self._store_id = store_id
        self._on_attach = on_attach
        self._query = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.search = QLineEdit()
        self.search.setObjectName("SearchInput")
        self.search.setPlaceholderText(strings.CUSTOMER_SEARCH_PLACEHOLDER)
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._on_text_changed)
        self.search.installEventFilter(self)
        layout.addWidget(self.search)

        # Frameless popup floating below the field (own top-level window so it
        # can overflow the host layout / dialog without being clipped).
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
        """Reset the field and hide the popup (host calls this after attach)."""
        self._debounce.stop()
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self._query = ""
        self._hide_popup()

    def set_focus(self) -> None:
        """Move keyboard focus into the search field."""
        self.search.setFocus()

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
            lambda: self._api.list_customers(
                self._store_id, query, limit=_SEARCH_LIMIT
            ),
            lambda customers: self._on_results(query, customers),
            self._on_error,
        )

    def _on_results(self, query: str, customers: object) -> None:
        # The widget (and its popup/list) may have been destroyed while the
        # search was in flight — e.g. the payment dialog was closed. Touching
        # the deleted C++ objects would hard-crash the process.
        if not shiboken6.isValid(self):
            return
        # A newer keystroke may have superseded this in-flight search.
        if query != self._query:
            return
        self.results.clear()
        for customer in customers or []:
            label = f"{customer['name']}   ·   {customer['phone']}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, customer)
            self.results.addItem(item)
        # Always offer an inline "create with this name" action.
        create = QListWidgetItem(strings.CUSTOMER_SEARCH_CREATE.format(query=query))
        create.setData(_CREATE_ROLE, True)
        if not (customers or []):
            create.setToolTip(strings.CUSTOMER_SEARCH_NO_RESULT)
        self.results.addItem(create)
        self.results.setCurrentRow(0)
        self._show_popup()

    def _on_error(self, err) -> None:
        # A transient search failure just clears the popup; the host keeps
        # working and the operator can retry by typing. Errors that need a
        # decision surface elsewhere (attach/create dialogs).
        if not shiboken6.isValid(self):
            return
        self._hide_popup()

    # ------------------------------------------------------------ selection

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        self._activate(item)

    def _activate(self, item: QListWidgetItem | None) -> None:
        if item is None:
            return
        if item.data(_CREATE_ROLE):
            self._create_customer()
            return
        customer = item.data(Qt.ItemDataRole.UserRole)
        if customer:
            self._hide_popup()
            self._on_attach(customer)

    def _create_customer(self) -> None:
        self._hide_popup()
        dialog = CustomerFormDialog(self._api, self._store_id, parent=self.window())
        # Prefill the name with what the operator already typed.
        dialog.name_input.setText(self._query)
        dialog.phone_input.setFocus()
        if dialog.exec() and dialog.result_customer:
            self._on_attach(dialog.result_customer)

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
