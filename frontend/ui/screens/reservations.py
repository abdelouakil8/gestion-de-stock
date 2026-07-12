"""Réservations (mise de côté / layaway).

Lists reservations (filterable by status); a reservation holds stock for a
customer until it is finalized (converted to a sale via the payment dialog) or
cancelled (which restores the held stock). Active reservations past their
expiry date are flagged in red.

All network goes through run_api; nothing here blocks the UI thread.
"""

from decimal import Decimal

import qtawesome as qta
import shiboken6
from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from services.workers import run_api
from ui import format as fmt
from ui import strings
from ui.styles.tokens import NEUTRAL, SEMANTIC, SPACING
from ui.widgets.badge import Badge
from ui.widgets.customer_search import CustomerSearchBox
from ui.widgets.data_table import DataTable
from ui.widgets.modal import ModalDialog, ask_confirm, show_error
from ui.widgets.payment_dialogs import CheckoutPaymentDialog
from ui.widgets.product_search import ProductSearchBox
from ui.widgets.states import EmptyState, StatefulStack
from ui.widgets.toast import show_toast

_STATUS_KIND = {
    "active": "accent",
    "completed": "success",
    "cancelled": "neutral",
}
_STATUS_FILTERS = [
    ("active", "RESERVATION_FILTER_ACTIVE"),
    ("completed", "RESERVATION_FILTER_COMPLETED"),
    ("cancelled", "RESERVATION_FILTER_CANCELLED"),
    ("", "RESERVATION_FILTER_ALL"),
]


class _ItemRow(QWidget):
    """One product line in the new-reservation dialog: name + qty + remove."""

    def __init__(self, product: dict, on_remove) -> None:
        super().__init__()
        self.product = product
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACING["sm"])
        name = QLabel(product["name"])
        name.setStyleSheet("background: transparent;")
        layout.addWidget(name, stretch=1)
        available = int(product.get("stock_quantity", 0)) - int(
            product.get("reserved_quantity", 0)
        )
        avail = QLabel(strings.RESERVATION_AVAILABLE.format(n=max(0, available)))
        avail.setObjectName("Muted")
        layout.addWidget(avail)
        self.qty = QSpinBox()
        self.qty.setRange(1, max(1, available) if available > 0 else 1)
        layout.addWidget(self.qty)
        remove = QPushButton(qta.icon("fa5s.times", color=NEUTRAL["500"]), "")
        remove.setObjectName("Ghost")
        remove.clicked.connect(lambda: on_remove(self))
        layout.addWidget(remove)


class NewReservationDialog(ModalDialog):
    def __init__(self, api, store_id: str, parent=None) -> None:
        super().__init__(strings.RESERVATION_NEW_TITLE, parent)
        self.api = api
        self.store_id = store_id
        self.customer: dict | None = None
        self.result_reservation: dict | None = None
        self._rows: list[_ItemRow] = []
        self.setMinimumWidth(560)

        self.content.addWidget(QLabel(strings.RESERVATION_CUSTOMER))
        self.customer_label = QLabel(strings.RESERVATION_NO_CUSTOMER)
        self.customer_label.setObjectName("Secondary")
        self.content.addWidget(self.customer_label)
        self.customer_search = CustomerSearchBox(
            self.api, self.store_id, self._on_customer
        )
        self.content.addWidget(self.customer_search)

        self.content.addWidget(QLabel(strings.RESERVATION_ITEMS))
        self.product_search = ProductSearchBox(
            self.api,
            self.store_id,
            self._on_product,
            placeholder=strings.RESERVATION_ADD_PRODUCT,
        )
        self.content.addWidget(self.product_search)
        self._items_box = QVBoxLayout()
        self._items_box.setSpacing(SPACING["xs"])
        self.content.addLayout(self._items_box)

        form = QHBoxLayout()
        deposit_box = QVBoxLayout()
        deposit_box.addWidget(QLabel(strings.RESERVATION_DEPOSIT))
        self.deposit_input = QDoubleSpinBox()
        self.deposit_input.setDecimals(2)
        self.deposit_input.setMaximum(9_999_999.99)
        deposit_box.addWidget(self.deposit_input)
        form.addLayout(deposit_box)
        expiry_box = QVBoxLayout()
        expiry_box.addWidget(QLabel(strings.RESERVATION_EXPIRES))
        self.expiry_input = QDateEdit(QDate.currentDate().addDays(7))
        self.expiry_input.setCalendarPopup(True)
        self.expiry_input.setDisplayFormat("dd/MM/yyyy")
        expiry_box.addWidget(self.expiry_input)
        form.addLayout(expiry_box)
        self.content.addLayout(form)

        self.content.addWidget(QLabel(strings.RESERVATION_NOTES))
        self.notes_input = QLineEdit()
        self.content.addWidget(self.notes_input)

        self.ok_button.setText(strings.RESERVATION_CREATE)

    def _on_customer(self, customer: dict) -> None:
        self.customer = customer
        self.customer_label.setText(f"{customer['name']} · {customer['phone']}")
        self.customer_search.clear()

    def _on_product(self, product: dict) -> None:
        for row in self._rows:
            if row.product["id"] == product["id"]:
                return  # already added
        row = _ItemRow(product, self._remove_row)
        self._rows.append(row)
        self._items_box.addWidget(row)
        self.product_search.clear()
        self.fit_to_content()

    def _remove_row(self, row: _ItemRow) -> None:
        if row in self._rows:
            self._rows.remove(row)
        self._items_box.removeWidget(row)
        row.deleteLater()
        self.fit_to_content()

    def accept(self) -> None:
        if self.customer is None:
            show_error(self, strings.RESERVATION_CUSTOMER_REQUIRED)
            return
        if not self._rows:
            show_error(self, strings.RESERVATION_ITEMS_REQUIRED)
            return
        payload = {
            "store_id": self.store_id,
            "customer_id": self.customer["id"],
            "expires_at": self.expiry_input.date().toString("yyyy-MM-dd") + "T23:59:59",
            "deposit_amount": f"{self.deposit_input.value():.2f}",
            "notes": self.notes_input.text().strip() or None,
            "items": [
                {"product_id": row.product["id"], "quantity": row.qty.value()}
                for row in self._rows
            ],
        }
        self.ok_button.setEnabled(False)
        run_api(
            lambda: self.api.create_reservation(payload),
            self._on_saved,
            self._on_error,
        )

    def _on_saved(self, reservation: object) -> None:
        self.result_reservation = reservation
        super().accept()

    def _on_error(self, err) -> None:
        self.ok_button.setEnabled(True)
        show_error(self, err.message)


class ReservationsScreen(QWidget):
    def __init__(self, api, store_id: str, parent=None) -> None:
        super().__init__(parent)
        self.api = api
        self.store_id = store_id
        self.reservations: list[dict] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(*[SPACING["xl"]] * 4)
        layout.setSpacing(SPACING["md"])

        header = QHBoxLayout()
        title = QLabel(strings.RESERVATIONS_TITLE)
        title.setObjectName("ScreenTitle")
        header.addWidget(title)
        header.addStretch(1)
        self.status_combo = QComboBox()
        for value, key in _STATUS_FILTERS:
            self.status_combo.addItem(getattr(strings, key), value)
        self.status_combo.currentIndexChanged.connect(lambda _: self.refresh())
        header.addWidget(self.status_combo)
        new_button = QPushButton(
            qta.icon("fa5s.bookmark", color="white"), strings.RESERVATION_NEW
        )
        new_button.setObjectName("Primary")
        new_button.clicked.connect(self._new)
        header.addWidget(new_button)
        refresh_button = QPushButton(
            qta.icon("fa5s.sync", color=NEUTRAL["600"]), strings.REFRESH
        )
        refresh_button.clicked.connect(self.refresh)
        header.addWidget(refresh_button)
        layout.addLayout(header)

        self.table = DataTable(
            [
                strings.RESERVATION_COL_CUSTOMER,
                strings.RESERVATION_COL_ITEMS,
                strings.RESERVATION_COL_TOTAL,
                strings.RESERVATION_COL_DEPOSIT,
                strings.RESERVATION_COL_EXPIRES,
                strings.RESERVATION_COL_STATUS,
                strings.RESERVATION_COL_ACTIONS,
            ]
        )
        self.stack = StatefulStack(
            self.table, EmptyState("fa5s.bookmark", strings.RESERVATIONS_EMPTY)
        )
        layout.addWidget(self.stack, stretch=1)

    # ------------------------------------------------------------- loading

    def refresh(self) -> None:
        self.stack.show_loading()
        status = self.status_combo.currentData() or None
        run_api(
            lambda: self.api.list_reservations(self.store_id, status=status),
            self._on_loaded,
            self._on_error,
        )

    def _on_loaded(self, reservations: object) -> None:
        if not shiboken6.isValid(self):
            return
        self.reservations = list(reservations or [])
        if not self.reservations:
            self.stack.show_empty()
            return
        self.table.set_rows(
            [
                [
                    self._customer_text(r),
                    strings.RESERVATION_ITEMS_COUNT.format(n=len(r.get("items", []))),
                    fmt.fmt_money(r["total_amount"]),
                    fmt.fmt_money(r["deposit_amount"]),
                    "",  # expiry (widget)
                    "",  # status badge
                    "",  # actions
                ]
                for r in self.reservations
            ]
        )
        for row, reservation in enumerate(self.reservations):
            self.table.setCellWidget(row, 4, self._expiry_cell(reservation))
            self.table.setCellWidget(row, 5, self._status_cell(reservation))
            self.table.setCellWidget(row, 6, self._actions_cell(reservation))
        self.stack.show_content()

    def _on_error(self, err) -> None:
        if not shiboken6.isValid(self):
            return
        self.stack.show_empty()
        show_error(self, err.message)

    # ----------------------------------------------------------- cell parts

    @staticmethod
    def _customer_text(reservation: dict) -> str:
        name = reservation.get("customer_name") or "—"
        phone = reservation.get("customer_phone")
        return f"{name}\n{phone}" if phone else name

    @staticmethod
    def _expiry_cell(reservation: dict) -> QWidget:
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(SPACING["xs"], 2, SPACING["xs"], 2)
        label = QLabel(fmt.fmt_date(reservation.get("expires_at")))
        if reservation.get("is_expired"):
            label.setStyleSheet(
                f"color: {SEMANTIC['danger']}; font-weight: 700; "
                "background: transparent;"
            )
        else:
            label.setStyleSheet("background: transparent;")
        row.addWidget(label)
        row.addStretch(1)
        return holder

    def _status_cell(self, reservation: dict) -> QWidget:
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(SPACING["xs"], 2, SPACING["xs"], 2)
        status = reservation.get("status", "active")
        if reservation.get("is_expired"):
            row.addWidget(Badge(strings.RESERVATION_EXPIRED, "danger"))
        else:
            row.addWidget(
                Badge(
                    strings.RESERVATION_STATUS_LABELS.get(status, status),
                    _STATUS_KIND.get(status, "neutral"),
                )
            )
        row.addStretch(1)
        return holder

    def _actions_cell(self, reservation: dict) -> QWidget:
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(SPACING["xs"], 2, SPACING["xs"], 2)
        row.setSpacing(SPACING["xs"])
        active = reservation.get("status") == "active"
        finalize = QPushButton(
            qta.icon("fa5s.check", color="white"), strings.RESERVATION_FINALIZE
        )
        finalize.setObjectName("Primary")
        finalize.setEnabled(active)
        finalize.clicked.connect(lambda _=False, r=reservation: self._finalize(r))
        row.addWidget(finalize)
        cancel = QPushButton(strings.RESERVATION_CANCEL)
        cancel.setObjectName("Danger")
        cancel.setEnabled(active)
        cancel.clicked.connect(lambda _=False, r=reservation: self._cancel(r))
        row.addWidget(cancel)
        row.addStretch(1)
        return holder

    # ------------------------------------------------------------- actions

    def _new(self) -> None:
        dialog = NewReservationDialog(self.api, self.store_id, parent=self)
        if dialog.exec() and dialog.result_reservation:
            self.refresh()
            show_toast(self, strings.RESERVATION_CREATED_TOAST)

    def _finalize(self, reservation: dict) -> None:
        total = Decimal(str(reservation["total_amount"]))
        customer = {
            "id": reservation["customer_id"],
            "name": reservation.get("customer_name") or "",
            "phone": reservation.get("customer_phone") or "",
        }
        dialog = CheckoutPaymentDialog(
            self.api, self.store_id, total, customer=customer, parent=self
        )
        if not dialog.exec() or dialog.payment is None:
            return
        run_api(
            lambda: self.api.complete_reservation(reservation["id"], dialog.payment),
            self._on_finalized,
            self._on_error,
        )

    def _on_finalized(self, reservation: object) -> None:
        show_toast(self, strings.RESERVATION_FINALIZED_TOAST)
        window = self.window()
        if hasattr(window, "refresh_alerts_badge"):
            window.refresh_alerts_badge()
        self.refresh()

    def _cancel(self, reservation: dict) -> None:
        name = reservation.get("customer_name") or ""
        if not ask_confirm(self, strings.RESERVATION_CANCEL_CONFIRM.format(name=name)):
            return
        run_api(
            lambda: self.api.cancel_reservation(reservation["id"]),
            lambda _result: self._on_cancelled(),
            self._on_error,
        )

    def _on_cancelled(self) -> None:
        show_toast(self, strings.RESERVATION_CANCELLED_TOAST)
        self.refresh()
