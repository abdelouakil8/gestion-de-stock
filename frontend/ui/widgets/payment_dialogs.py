"""Payment dialogs.

CheckoutPaymentDialog — the Encaisser (F12) flow: full or partial payment;
a partial payment REQUIRES a customer (creatable right there) and an amount
strictly below the total, with the remaining balance shown live. The
server re-enforces every rule; this dialog only guides the cashier.

RecordPaymentDialog — a later payment on a credit sale (Clients / Alertes):
amount defaults to the remaining balance; overpayment is blocked client-
side for guidance and rejected server-side authoritatively.
"""

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from services.workers import run_api
from ui import format as fmt
from ui import strings
from ui.styles.tokens import SPACING
from ui.widgets.customer_search import CustomerSearchBox
from ui.widgets.modal import ModalDialog, show_error


class _MoneySpin(QDoubleSpinBox):
    def __init__(self, maximum: float, parent=None) -> None:
        super().__init__(parent)
        self.setDecimals(2)
        self.setRange(0.0, maximum)
        self.setAlignment(Qt.AlignmentFlag.AlignRight)

    def decimal(self) -> Decimal:
        return Decimal(f"{self.value():.2f}")


class CheckoutPaymentDialog(ModalDialog):
    """Returns .payment (dict for the API) and .customer when accepted."""

    def __init__(
        self,
        api,
        store_id: str,
        total: Decimal,
        customer: dict | None = None,
        parent=None,
    ) -> None:
        super().__init__(strings.PAYMENT_TITLE, parent)
        self.api = api
        self.store_id = store_id
        self.total = total
        self.customer = customer
        self.payment: dict | None = None

        total_row = QHBoxLayout()
        total_row.addWidget(QLabel(strings.PAYMENT_TOTAL_LABEL))
        total_label = QLabel(fmt.fmt_money(total))
        total_label.setObjectName("TotalAmount")
        total_row.addStretch(1)
        total_row.addWidget(total_label)
        self.content.addLayout(total_row)

        method_row = QHBoxLayout()
        method_row.addWidget(QLabel(strings.PAYMENT_METHOD_LABEL))
        self.method_combo = QComboBox()
        for key, label in strings.PAYMENT_METHOD_LABELS.items():
            self.method_combo.addItem(label, key)
        method_row.addWidget(self.method_combo, stretch=1)
        self.content.addLayout(method_row)

        self.full_radio = QRadioButton(strings.PAYMENT_FULL)
        self.full_radio.setChecked(True)
        self.partial_radio = QRadioButton(strings.PAYMENT_PARTIAL)
        self.content.addWidget(self.full_radio)
        self.content.addWidget(self.partial_radio)

        # Partial section (hidden until the partial mode is chosen).
        self.partial_box = QWidget()
        partial_layout = QVBoxLayout(self.partial_box)
        partial_layout.setContentsMargins(SPACING["lg"], 0, 0, 0)
        partial_layout.setSpacing(SPACING["sm"])

        amount_row = QHBoxLayout()
        amount_row.addWidget(QLabel(strings.PAYMENT_AMOUNT_LABEL))
        self.amount_input = _MoneySpin(max(0.0, float(total) - 0.01))
        self.amount_input.valueChanged.connect(self._update_remaining)
        amount_row.addWidget(self.amount_input, stretch=1)
        partial_layout.addLayout(amount_row)

        self.remaining_label = QLabel("")
        self.remaining_label.setObjectName("FieldHint")
        partial_layout.addWidget(self.remaining_label)

        # Attached-customer line (shown once a customer is picked/created).
        customer_row = QHBoxLayout()
        customer_row.addWidget(QLabel(strings.CHECKOUT_CUSTOMER_LABEL))
        self.customer_label = QLabel("")
        self.customer_label.setObjectName("Secondary")
        customer_row.addWidget(self.customer_label, stretch=1)
        partial_layout.addLayout(customer_row)

        # Attach an existing customer (search by name/phone).
        partial_layout.addWidget(QLabel(strings.PAYMENT_ATTACH_EXISTING))
        self.customer_search = CustomerSearchBox(
            self.api, self.store_id, self._on_customer_attached
        )
        partial_layout.addWidget(self.customer_search)

        # ...or create a new one inline with name + phone.
        partial_layout.addWidget(QLabel(strings.PAYMENT_CREATE_NEW))
        self.new_name_input = QLineEdit()
        self.new_name_input.setPlaceholderText(strings.PAYMENT_NEW_CUSTOMER_NAME)
        partial_layout.addWidget(self.new_name_input)
        self.new_phone_input = QLineEdit()
        self.new_phone_input.setPlaceholderText(strings.PAYMENT_NEW_CUSTOMER_PHONE)
        partial_layout.addWidget(self.new_phone_input)

        self.customer_hint = QLabel(strings.PAYMENT_CUSTOMER_REQUIRED)
        self.customer_hint.setObjectName("FieldError")
        self.customer_hint.setWordWrap(True)
        partial_layout.addWidget(self.customer_hint)

        self.content.addWidget(self.partial_box)
        self.partial_box.setVisible(False)
        self.partial_radio.toggled.connect(self._on_mode_changed)

        self.ok_button.setText(strings.PAYMENT_CONFIRM)
        self._refresh_customer()
        self._update_remaining()
        self.ok_button.setFocus()

    # ------------------------------------------------------------ helpers

    def _on_mode_changed(self, partial: bool) -> None:
        self.partial_box.setVisible(partial)
        if partial:
            self.amount_input.setFocus()
            self.amount_input.selectAll()
        # The partial block is shown/hidden after first layout — grow/shrink
        # the dialog to fit it (a plain adjustSize can't, the scroll area's
        # size hint is frozen from construction).
        self.fit_to_content()

    def _on_customer_attached(self, customer: dict) -> None:
        self.customer = customer
        self.customer_search.clear()
        self._refresh_customer()

    def _refresh_customer(self) -> None:
        if self.customer:
            self.customer_label.setText(
                f"{self.customer['name']} · {self.customer['phone']}"
            )
            # A customer is attached: hide the attach/create affordances.
            self.customer_search.hide()
            self.new_name_input.hide()
            self.new_phone_input.hide()
            self.customer_hint.setVisible(False)
        else:
            self.customer_label.setText(strings.CHECKOUT_CUSTOMER_ANONYMOUS)
            self.customer_search.show()
            self.new_name_input.show()
            self.new_phone_input.show()
            self.customer_hint.setVisible(True)

    def _update_remaining(self) -> None:
        remaining = self.total - self.amount_input.decimal()
        self.remaining_label.setText(
            f"{strings.PAYMENT_REMAINING_LABEL} : {fmt.fmt_money(remaining)}"
        )

    # ------------------------------------------------------------- accept

    def _selected_method(self) -> str:
        return self.method_combo.currentData() or "cash"

    def accept(self) -> None:
        if self.full_radio.isChecked():
            self.payment = {"mode": "full", "payment_method": self._selected_method()}
            if self.customer:
                self.payment["customer_id"] = self.customer["id"]
            super().accept()
            return
        # Partial: customer mandatory, amount < total (server re-checks).
        amount = self.amount_input.decimal()
        if amount >= self.total:
            show_error(self, strings.PAYMENT_AMOUNT_TOO_HIGH)
            return
        if self.customer:
            self._finish_partial(self.customer["id"])
            return
        # No attached customer: try to create one inline from name + phone.
        name = self.new_name_input.text().strip()
        phone = self.new_phone_input.text().strip()
        if not name or not phone:
            show_error(self, strings.PAYMENT_CUSTOMER_REQUIRED)
            return
        self.ok_button.setEnabled(False)
        run_api(
            lambda: self.api.create_customer(
                {"store_id": self.store_id, "name": name, "phone": phone}
            ),
            self._on_customer_created,
            self._on_create_error,
        )

    def _on_customer_created(self, customer: object) -> None:
        self.customer = customer
        self.ok_button.setEnabled(True)
        self._finish_partial(customer["id"])

    def _on_create_error(self, err) -> None:
        self.ok_button.setEnabled(True)
        show_error(self, err.message)

    def _finish_partial(self, customer_id: str) -> None:
        amount = self.amount_input.decimal()
        self.payment = {
            "mode": "partial",
            "amount_paid": f"{amount:.2f}",
            "customer_id": customer_id,
            "payment_method": self._selected_method(),
        }
        super().accept()


class RecordPaymentDialog(ModalDialog):
    """Record an instalment on a sale with an outstanding balance."""

    def __init__(self, api, sale: dict, parent=None) -> None:
        super().__init__(strings.PAYMENT_RECORD_TITLE, parent)
        self.api = api
        self.sale = sale
        self.result_sale: dict | None = None
        balance = Decimal(sale["total_amount"]) - Decimal(sale["paid_amount"])
        self.balance = balance

        balance_label = QLabel(
            strings.PAYMENT_RECORD_BALANCE.format(balance=fmt.fmt_money(balance))
        )
        balance_label.setObjectName("Secondary")
        self.content.addWidget(balance_label)

        amount_row = QHBoxLayout()
        amount_row.addWidget(QLabel(strings.PAYMENT_AMOUNT_LABEL))
        self.amount_input = _MoneySpin(float(balance))
        self.amount_input.setValue(float(balance))  # settle in full by default
        amount_row.addWidget(self.amount_input, stretch=1)
        self.content.addLayout(amount_row)

        method_row = QHBoxLayout()
        method_row.addWidget(QLabel(strings.PAYMENT_METHOD_LABEL))
        self.method_combo = QComboBox()
        for key, label in strings.PAYMENT_METHOD_LABELS.items():
            self.method_combo.addItem(label, key)
        method_row.addWidget(self.method_combo, stretch=1)
        self.content.addLayout(method_row)

        self.ok_button.setText(strings.PAYMENT_CONFIRM)
        self.amount_input.setFocus()
        self.amount_input.selectAll()

    def accept(self) -> None:
        amount = self.amount_input.decimal()
        if amount <= 0:
            show_error(self, strings.PAYMENT_AMOUNT_REQUIRED)
            return
        if amount > self.balance:
            show_error(self, strings.PAYMENT_AMOUNT_TOO_HIGH)
            return
        self.ok_button.setEnabled(False)
        method = self.method_combo.currentData() or "cash"
        run_api(
            lambda: self.api.record_payment(
                self.sale["id"], f"{amount:.2f}", method
            ),
            self._on_done,
            self._on_error,
        )

    def _on_done(self, sale: object) -> None:
        self.result_sale = sale
        super().accept()

    def _on_error(self, err) -> None:
        self.ok_button.setEnabled(True)
        show_error(self, err.message)
