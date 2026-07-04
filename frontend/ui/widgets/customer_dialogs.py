"""Customer create/edit form dialog, shared by the Caisse (attach customer /
credit payment via CustomerSearchBox) and the Clients screen.

Search-and-attach lives in ui.widgets.customer_search.CustomerSearchBox; the
old CustomerPickerDialog it replaced has been removed."""

import shiboken6
from PySide6.QtWidgets import QFormLayout, QLineEdit

from services.workers import run_api
from ui import strings
from ui.styles.tokens import SPACING
from ui.widgets.modal import ModalDialog, show_error


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

        form = QFormLayout()
        form.setSpacing(SPACING["md"])
        self.name_input = QLineEdit()
        self.phone_input = QLineEdit()
        self.note_input = QLineEdit()
        form.addRow(strings.CUSTOMER_NAME, self.name_input)
        form.addRow(strings.CUSTOMER_PHONE, self.phone_input)
        form.addRow(strings.CUSTOMER_NOTE, self.note_input)
        self.content.addLayout(form)

        if customer:
            self.name_input.setText(customer["name"])
            self.phone_input.setText(customer["phone"])
            self.note_input.setText(customer.get("note") or "")
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
