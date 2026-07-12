"""Reusable owner-PIN confirmation dialog.

Same pattern as the factory-reset / backup-restore dialogs in
settings_screen: a masked field whose freshly typed PIN is verified
server-side (never a cached credential). On success the verified PIN is left
on ``self.pin`` for the caller to forward to the gated action.
"""

from PySide6.QtWidgets import QLabel, QLineEdit

from services.workers import run_api
from ui import strings
from ui.widgets.modal import ModalDialog, show_error


class PinConfirmDialog(ModalDialog):
    """Ask for the owner PIN and verify it before an owner action.

    Usage:
        dlg = PinConfirmDialog(api, prompt=..., parent=self)
        if dlg.exec():
            do_owner_thing(pin=dlg.pin)
    """

    def __init__(self, api, prompt: str | None = None, parent=None) -> None:
        super().__init__(strings.PIN_CONFIRM_TITLE, parent)
        self.api = api
        self.pin: str | None = None

        label = QLabel(prompt or strings.PIN_CONFIRM_PROMPT)
        label.setWordWrap(True)
        self.content.addWidget(label)

        self.pin_input = QLineEdit()
        self.pin_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pin_input.setPlaceholderText(strings.LOGIN_PLACEHOLDER)
        self.pin_input.textChanged.connect(
            lambda text: self.ok_button.setEnabled(bool(text.strip()))
        )
        self.pin_input.returnPressed.connect(self.accept)
        self.content.addWidget(self.pin_input)

        self.ok_button.setText(strings.PIN_CONFIRM_BUTTON)
        self.ok_button.setEnabled(False)
        self.pin_input.setFocus()

    def accept(self) -> None:
        pin = self.pin_input.text().strip()
        if not pin:
            return
        self.ok_button.setEnabled(False)
        run_api(
            lambda: self.api.verify_pin(pin),
            lambda _result, p=pin: self._on_ok(p),
            self._on_error,
        )

    def _on_ok(self, pin: str) -> None:
        self.pin = pin
        super().accept()

    def _on_error(self, err) -> None:
        self.ok_button.setEnabled(True)
        show_error(self, strings.PIN_CONFIRM_WRONG)
        self.pin_input.selectAll()
        self.pin_input.setFocus()
