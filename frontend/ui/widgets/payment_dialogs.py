"""Payment dialogs.

CheckoutPaymentDialog — the Encaisser (F12) flow: full or partial payment;
a partial payment REQUIRES a customer (creatable right there) and an amount
strictly below the total, with the remaining balance shown live. The
server re-enforces every rule; this dialog only guides the cashier.

RecordPaymentDialog — a later payment on a credit sale (Clients / Alertes):
amount defaults to the remaining balance; overpayment is blocked client-
side for guidance and rejected server-side authoritatively.
"""

from collections.abc import Callable
from decimal import Decimal

import qtawesome as qta
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QDoubleSpinBox,
    QFrame,
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
from ui.styles import tokens
from ui.styles.tokens import NEUTRAL, SPACING
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


class _ModeOption(QFrame):
    """A selectable payment-mode card: a radio with a title + short hint.

    The whole card is clickable (not just the tiny radio dot) and lights up
    when selected via the #OptionCard[selected] QSS variant."""

    def __init__(
        self, title: str, hint: str, on_click: Callable[[], None], parent=None
    ) -> None:
        super().__init__(parent)
        self.setObjectName("OptionCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._on_click = on_click

        # Hidden radio holds the exclusive state; we paint our OWN circular
        # indicator with qtawesome (a QSS-styled radio indicator renders an
        # ugly square border when checked, which is what the operator saw).
        self.radio = QRadioButton(self)
        self.radio.hide()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(
            SPACING["md"], SPACING["sm"], SPACING["md"], SPACING["sm"]
        )
        layout.setSpacing(SPACING["md"])

        self._indicator = QLabel()
        self._indicator.setFixedSize(24, 24)
        self._indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._indicator, alignment=Qt.AlignmentFlag.AlignVCenter)

        texts = QVBoxLayout()
        texts.setContentsMargins(0, 0, 0, 0)
        texts.setSpacing(0)
        title_label = QLabel(title)
        title_label.setObjectName("OptionTitle")
        texts.addWidget(title_label)
        hint_label = QLabel(hint)
        hint_label.setObjectName("Muted")
        texts.addWidget(hint_label)
        layout.addLayout(texts, stretch=1)

        self.set_selected(False)

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", "true" if selected else "false")
        self.style().unpolish(self)
        self.style().polish(self)
        if selected:
            icon = qta.icon("fa5s.check-circle", color=tokens.CURRENT_ACCENT)
        else:
            icon = qta.icon("fa5.circle", color=NEUTRAL["400"])
        self._indicator.setPixmap(icon.pixmap(22, 22))

    def mousePressEvent(self, event) -> None:
        self._on_click()
        super().mousePressEvent(event)


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

        # Total-to-pay hero band.
        total_card = QFrame()
        total_card.setObjectName("PayTotalCard")
        total_card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        total_row = QHBoxLayout(total_card)
        total_row.setContentsMargins(
            SPACING["md"], SPACING["sm"], SPACING["md"], SPACING["sm"]
        )
        total_caption = QLabel(strings.PAYMENT_TOTAL_LABEL)
        total_caption.setObjectName("Secondary")
        total_row.addWidget(total_caption)
        total_label = QLabel(fmt.fmt_money(total))
        total_label.setObjectName("TotalAmount")
        total_row.addStretch(1)
        total_row.addWidget(total_label)
        self.content.addWidget(total_card)

        # Payment mode — two exclusive, fully clickable option cards.
        self._mode_group = QButtonGroup(self)
        self._mode_group.setExclusive(True)
        self.full_option = _ModeOption(
            strings.PAYMENT_FULL,
            strings.PAYMENT_FULL_HINT,
            lambda: self.full_radio.setChecked(True),
        )
        self.partial_option = _ModeOption(
            strings.PAYMENT_PARTIAL,
            strings.PAYMENT_PARTIAL_HINT,
            lambda: self.partial_radio.setChecked(True),
        )
        self.full_radio = self.full_option.radio
        self.partial_radio = self.partial_option.radio
        self._mode_group.addButton(self.full_radio)
        self._mode_group.addButton(self.partial_radio)
        self.content.addWidget(self.full_option)
        self.content.addWidget(self.partial_option)
        self.full_radio.setChecked(True)

        # Partial section (hidden until the partial mode is chosen).
        self.partial_box = QWidget()
        partial_layout = QVBoxLayout(self.partial_box)
        partial_layout.setContentsMargins(0, SPACING["xs"], 0, 0)
        partial_layout.setSpacing(SPACING["sm"])

        amount_label = QLabel(strings.PAYMENT_AMOUNT_LABEL)
        amount_label.setObjectName("Caption")
        partial_layout.addWidget(amount_label)
        self.amount_input = _MoneySpin(max(0.0, float(total) - 0.01))
        self.amount_input.setObjectName("MoneyInput")
        self.amount_input.valueChanged.connect(self._update_remaining)
        partial_layout.addWidget(self.amount_input)

        self.remaining_label = QLabel("")
        self.remaining_label.setObjectName("RemainingHint")
        partial_layout.addWidget(self.remaining_label)

        divider = QFrame()
        divider.setObjectName("HDivider")
        divider.setFixedHeight(1)
        partial_layout.addWidget(divider)

        client_head = QLabel(strings.PAYMENT_CLIENT_SECTION)
        client_head.setObjectName("Caption")
        partial_layout.addWidget(client_head)

        # Attached-customer line (shown once a customer is picked/created).
        customer_row = QHBoxLayout()
        customer_row.addWidget(QLabel(strings.CHECKOUT_CUSTOMER_LABEL))
        self.customer_label = QLabel("")
        self.customer_label.setObjectName("Secondary")
        customer_row.addWidget(self.customer_label, stretch=1)
        partial_layout.addLayout(customer_row)

        # Attach an existing customer (search by name/phone).
        self.attach_existing_label = QLabel(strings.PAYMENT_ATTACH_EXISTING)
        self.attach_existing_label.setObjectName("Muted")
        partial_layout.addWidget(self.attach_existing_label)
        self.customer_search = CustomerSearchBox(
            self.api, self.store_id, self._on_customer_attached
        )
        partial_layout.addWidget(self.customer_search)

        # ...or create a new one inline with name + phone (one tidy row).
        self.create_new_label = QLabel(strings.PAYMENT_CREATE_NEW)
        self.create_new_label.setObjectName("Muted")
        partial_layout.addWidget(self.create_new_label)
        name_phone_row = QHBoxLayout()
        name_phone_row.setSpacing(SPACING["sm"])
        self.new_name_input = QLineEdit()
        self.new_name_input.setPlaceholderText(strings.PAYMENT_NEW_CUSTOMER_NAME)
        name_phone_row.addWidget(self.new_name_input, stretch=3)
        self.new_phone_input = QLineEdit()
        self.new_phone_input.setPlaceholderText(strings.PAYMENT_NEW_CUSTOMER_PHONE)
        name_phone_row.addWidget(self.new_phone_input, stretch=2)
        partial_layout.addLayout(name_phone_row)

        self.customer_hint = QLabel(strings.PAYMENT_CUSTOMER_REQUIRED)
        self.customer_hint.setObjectName("FieldError")
        self.customer_hint.setWordWrap(True)
        partial_layout.addWidget(self.customer_hint)

        self.content.addWidget(self.partial_box)
        self.partial_box.setVisible(False)
        self.partial_radio.toggled.connect(self._on_mode_changed)
        self._mode_group.buttonToggled.connect(lambda *_: self._refresh_mode_cards())

        self.ok_button.setText(strings.PAYMENT_CONFIRM)
        self._refresh_mode_cards()
        self._refresh_customer()
        self._update_remaining()
        self.ok_button.setFocus()

    def _refresh_mode_cards(self) -> None:
        self.full_option.set_selected(self.full_radio.isChecked())
        self.partial_option.set_selected(self.partial_radio.isChecked())

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
        attached = bool(self.customer)
        if attached:
            self.customer_label.setText(
                f"{self.customer['name']} · {self.customer['phone']}"
            )
        else:
            self.customer_label.setText(strings.CHECKOUT_CUSTOMER_ANONYMOUS)
        # A customer is attached -> hide every attach/create affordance;
        # otherwise show the search + inline-create fields.
        for widget in (
            self.attach_existing_label,
            self.customer_search,
            self.create_new_label,
            self.new_name_input,
            self.new_phone_input,
        ):
            widget.setVisible(not attached)
        self.customer_hint.setVisible(not attached)
        # Attaching/detaching changes the block height while it is shown.
        if self.partial_box.isVisible():
            self.fit_to_content()

    def _update_remaining(self) -> None:
        remaining = self.total - self.amount_input.decimal()
        self.remaining_label.setText(
            f"{strings.PAYMENT_REMAINING_LABEL} : {fmt.fmt_money(remaining)}"
        )

    # ------------------------------------------------------------- accept

    def accept(self) -> None:
        if self.full_radio.isChecked():
            self.payment = {"mode": "full", "payment_method": "cash"}
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
            "payment_method": "cash",
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
        run_api(
            lambda: self.api.record_payment(
                self.sale["id"], f"{amount:.2f}", "cash"
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
