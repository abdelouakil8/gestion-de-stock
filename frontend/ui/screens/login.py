"""PIN gate shown at application start (Phase 3 local auth, UI side)."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLabel, QLineEdit, QPushButton, QVBoxLayout

from services.workers import run_api
from ui import strings
from ui.styles.tokens import SPACING


class LoginDialog(QDialog):
    """Verifies the PIN against the API. On success, the PIN stays on the
    ApiClient (in memory only) to authorize owner actions."""

    def __init__(self, api, parent=None) -> None:
        super().__init__(parent)
        self.api = api
        self.setWindowTitle(strings.LOGIN_TITLE)
        self.setModal(True)
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(*[SPACING["xl"]] * 4)
        layout.setSpacing(SPACING["md"])

        layout.addWidget(QLabel(strings.LOGIN_PROMPT))
        self.pin_input = QLineEdit()
        self.pin_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pin_input.setPlaceholderText(strings.LOGIN_PLACEHOLDER)
        self.pin_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pin_input.returnPressed.connect(self._verify)
        layout.addWidget(self.pin_input)

        self.feedback = QLabel("")
        self.feedback.setObjectName("Muted")
        self.feedback.setWordWrap(True)
        layout.addWidget(self.feedback)

        self.open_button = QPushButton(strings.LOGIN_BUTTON)
        self.open_button.setObjectName("Primary")
        self.open_button.clicked.connect(self._verify)
        layout.addWidget(self.open_button)

        self.pin_input.setFocus()

    def _verify(self) -> None:
        pin = self.pin_input.text().strip()
        if not pin:
            return
        self.open_button.setEnabled(False)
        run_api(
            lambda: self.api.verify_pin(pin),
            lambda _: self._on_valid(pin),
            self._on_error,
        )

    def _on_valid(self, pin: str) -> None:
        self.api.pin = pin
        self.accept()

    def _on_error(self, err) -> None:
        self.open_button.setEnabled(True)
        if err.code == "pin_not_configured":
            # No PIN set: open unprotected, owner actions will explain why.
            self.feedback.setText(strings.PIN_NOT_CONFIGURED)
            self.api.pin = None
            self.accept()
            return
        self.feedback.setText(err.message)
        self.pin_input.selectAll()
        self.pin_input.setFocus()
