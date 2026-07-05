"""First-run onboarding wizard."""

import qtawesome as qta
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
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


class OnboardingWizard(QDialog):
    """First-run setup wizard. Currently only asks to set the initial PIN."""

    def __init__(self, api, parent=None) -> None:
        super().__init__(parent)
        self.api = api
        self.setWindowTitle(strings.ONBOARDING_TITLE)
        self.setModal(True)
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(*[SPACING["xl"]] * 4)
        layout.setSpacing(SPACING["lg"])

        # Welcome Header
        brand_icon = QLabel()
        brand_icon.setPixmap(
            qta.icon("fa5s.store", color=tokens.CURRENT_ACCENT).pixmap(48, 48)
        )
        brand_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(brand_icon)
        
        title = QLabel(strings.ONBOARDING_WELCOME)
        title.setObjectName("ScreenTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        desc = QLabel(strings.ONBOARDING_DESC)
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(desc)
        
        layout.addSpacing(SPACING["md"])

        # PIN Form
        prompt = QLabel(strings.ONBOARDING_PIN_PROMPT)
        layout.addWidget(prompt)
        
        self.pin_input = QLineEdit()
        self.pin_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pin_input.setPlaceholderText(strings.LOGIN_PLACEHOLDER)
        self.pin_input.returnPressed.connect(self._submit)
        layout.addWidget(self.pin_input)
        
        self.pin_confirm = QLineEdit()
        self.pin_confirm.setEchoMode(QLineEdit.EchoMode.Password)
        self.pin_confirm.setPlaceholderText(strings.ONBOARDING_PIN_CONFIRM)
        self.pin_confirm.returnPressed.connect(self._submit)
        layout.addWidget(self.pin_confirm)

        self.feedback = QLabel("")
        self.feedback.setObjectName("Danger")
        self.feedback.setWordWrap(True)
        layout.addWidget(self.feedback)

        self.submit_button = QPushButton(strings.ONBOARDING_SUBMIT)
        self.submit_button.setObjectName("Primary")
        self.submit_button.clicked.connect(self._submit)
        layout.addWidget(self.submit_button)

        self.pin_input.setFocus()

    def _submit(self) -> None:
        pin = self.pin_input.text().strip()
        confirm = self.pin_confirm.text().strip()
        
        if not pin:
            self.feedback.setText(strings.ONBOARDING_ERR_EMPTY)
            return
            
        if pin != confirm:
            self.feedback.setText(strings.ONBOARDING_ERR_MISMATCH)
            return
            
        self.submit_button.setEnabled(False)
        self.feedback.setText("")
        
        run_api(
            lambda: self.api.set_initial_pin(pin),
            lambda _: self._on_success(pin),
            self._on_error,
        )

    def _on_success(self, pin: str) -> None:
        self.api.pin = pin
        self.accept()

    def _on_error(self, err) -> None:
        self.submit_button.setEnabled(True)
        self.feedback.setText(err.message)
        self.pin_input.selectAll()
        self.pin_input.setFocus()
