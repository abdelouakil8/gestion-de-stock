"""Customer create/edit form dialog, shared by the Caisse (attach customer /
credit payment via CustomerSearchBox) and the Clients screen.

Search-and-attach lives in ui.widgets.customer_search.CustomerSearchBox; the
old CustomerPickerDialog it replaced has been removed."""

import shiboken6
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from services.workers import run_api
from ui import strings
from ui.styles.tokens import SPACING
from ui.widgets.modal import ModalDialog, show_error


def _labeled_field(label_text: str, widget: QWidget) -> QVBoxLayout:
    """Label-above-input vertical pair used in every form field."""
    lbl = QLabel(label_text)
    lbl.setObjectName("Caption")
    box = QVBoxLayout()
    box.setSpacing(SPACING["xs"])
    box.addWidget(lbl)
    box.addWidget(widget)
    return box


class CustomerFormDialog(ModalDialog):
    """Create/edit a customer. `customer` present ⇒ edit mode."""

    def __init__(self, api, store_id: str, customer: dict | None = None, parent=None):
        title = (
            strings.CUSTOMER_DIALOG_EDIT if customer else strings.CUSTOMER_DIALOG_NEW
        )
        super().__init__(title, parent)
        self.api = api
        self.store_id = store_id
        self.customer = customer
        self.result_customer: dict | None = None
        self.setMinimumWidth(480)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText(strings.CUSTOMER_NAME)
        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText(strings.CUSTOMER_PHONE)
        self.note_input = QLineEdit()
        self.level_combo = QComboBox()
        self.level_combo.addItem(strings.CUSTOMER_PRICE_LEVEL_NONE, None)
        for value in ("detail", "gros", "super_gros"):
            self.level_combo.addItem(strings.PRICE_LEVEL_LABELS[value], value)

        # Identity: name + phone side by side (the two required fields).
        identity_row = QHBoxLayout()
        identity_row.setSpacing(SPACING["md"])
        identity_row.addLayout(
            _labeled_field(strings.CUSTOMER_NAME, self.name_input), stretch=3
        )
        identity_row.addLayout(
            _labeled_field(strings.CUSTOMER_PHONE, self.phone_input), stretch=2
        )
        self.content.addLayout(identity_row)

        divider = QFrame()
        divider.setObjectName("HDivider")
        divider.setFixedHeight(1)
        self.content.addWidget(divider)

        self.content.addLayout(_labeled_field(strings.CUSTOMER_NOTE, self.note_input))
        self.content.addLayout(
            _labeled_field(strings.CUSTOMER_DEFAULT_PRICE_LEVEL, self.level_combo)
        )

        if customer:
            self.name_input.setText(customer["name"])
            self.phone_input.setText(customer["phone"])
            self.note_input.setText(customer.get("note") or "")
            index = self.level_combo.findData(customer.get("default_price_level"))
            if index >= 0:
                self.level_combo.setCurrentIndex(index)
        self.name_input.setFocus()

    def accept(self) -> None:  # validation + API call, stays open on error
        name = self.name_input.text().strip()
        phone = self.phone_input.text().strip()
        if not name or not phone:
            show_error(self, strings.REQUIRED_FIELD)
            return
        payload = {
            "name": name,
            "phone": phone,
            "note": self.note_input.text().strip() or None,
            "default_price_level": self.level_combo.currentData(),
        }
        self.ok_button.setEnabled(False)
        if self.customer:
            customer_id = self.customer["id"]
            call = lambda: self.api.update_customer(customer_id, payload)  # noqa: E731
        else:
            payload["store_id"] = self.store_id
            call = lambda: self.api.create_customer(payload)  # noqa: E731
        run_api(call, self._on_saved, self._on_error)

    def _on_saved(self, customer: object) -> None:
        if not shiboken6.isValid(self):
            return  # dialog dismissed while the save was in flight
        self.result_customer = customer
        super().accept()

    def _on_error(self, err) -> None:
        if not shiboken6.isValid(self):
            return
        self.ok_button.setEnabled(True)
        show_error(self, err.message)
