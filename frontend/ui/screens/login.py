"""PIN gate shown at application start.

Multi-user (Phase 17): the operator picks their name from a list, enters their
PIN and receives a session token stored on the ApiClient. When no named users
exist yet (a fresh single-PIN install), the picker is hidden and the dialog
falls back to the legacy PIN verification so nobody is locked out.
"""

import qtawesome as qta
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from services.workers import run_api
from ui import strings
from ui.styles import tokens
from ui.styles.tokens import SPACING


def _role_label(role: str) -> str:
    return strings.ROLE_LABELS.get(role, role)


class LoginDialog(QDialog):
    """On success the session token (or, in legacy mode, the PIN) stays on the
    ApiClient in memory to authorize the session."""

    def __init__(self, api, parent=None) -> None:
        super().__init__(parent)
        self.api = api
        self._users: list[dict] = []
        self.setWindowTitle(strings.LOGIN_TITLE)
        self.setModal(True)
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(*[SPACING["xl"]] * 4)
        layout.setSpacing(SPACING["md"])

        brand_icon = QLabel()
        brand_icon.setPixmap(
            qta.icon("fa5s.store", color=tokens.CURRENT_ACCENT).pixmap(40, 40)
        )
        brand_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand_icon.setStyleSheet("background: transparent;")
        layout.addWidget(brand_icon)
        brand_name = QLabel(strings.APP_TITLE)
        brand_name.setObjectName("ScreenTitle")
        brand_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(brand_name)
        layout.addSpacing(SPACING["sm"])

        # User picker — populated from the public login list.
        self.user_combo = QComboBox()
        self.user_combo.currentIndexChanged.connect(self._update_greeting)
        self.user_combo.hide()
        layout.addWidget(self.user_combo)

        self.greeting = QLabel("")
        self.greeting.setObjectName("Secondary")
        self.greeting.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.greeting)

        prompt = QLabel(strings.LOGIN_PROMPT)
        prompt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(prompt)
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
        run_api(self.api.list_login_users, self._on_users, lambda err: None)

    # --------------------------------------------------------------- users

    def _on_users(self, users: object) -> None:
        self._users = list(users or [])
        if not self._users:
            self.user_combo.hide()  # legacy single-PIN mode
            return
        self.user_combo.blockSignals(True)
        self.user_combo.clear()
        for user in self._users:
            self.user_combo.addItem(
                f"{user['name']} · {_role_label(user['role'])}", user
            )
        self.user_combo.blockSignals(False)
        self.user_combo.show()
        self._update_greeting()

    def _update_greeting(self) -> None:
        user = self.user_combo.currentData()
        if user:
            self.greeting.setText(strings.LOGIN_GREETING.format(name=user["name"]))

    # -------------------------------------------------------------- verify

    def _verify(self) -> None:
        if not self.open_button.isEnabled():
            return
        pin = self.pin_input.text().strip()
        if not pin:
            return
        self.open_button.setEnabled(False)
        user = self.user_combo.currentData()
        if user:
            run_api(
                lambda: self.api.login(user["id"], pin),
                lambda _result: self.accept(),
                self._on_error,
            )
        else:
            # Legacy: no named users — verify the single PIN.
            run_api(
                lambda: self.api.verify_pin(pin),
                lambda _result: self._on_legacy_valid(pin),
                self._on_error,
            )

    def _on_legacy_valid(self, pin: str) -> None:
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
