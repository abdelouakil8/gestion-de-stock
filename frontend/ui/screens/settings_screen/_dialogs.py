"""Supporting dialogs and widgets for the settings screen."""

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from services.workers import run_api
from ui import strings
from ui.styles.tokens import SPACING
from ui.widgets.modal import ModalDialog, show_error


class FactoryResetDialog(ModalDialog):
    """Type-your-PIN confirmation for the full wipe. The typed PIN is sent
    to the server, which is the only judge — no cached credential reuse."""

    def __init__(self, api, parent=None) -> None:
        super().__init__(strings.RESET_DIALOG_TITLE, parent)
        self.api = api
        self.reset_done = False

        warning = QLabel(strings.RESET_DIALOG_WARNING)
        warning.setObjectName("FieldError")
        warning.setWordWrap(True)
        self.content.addWidget(warning)

        self.content.addWidget(QLabel(strings.RESET_DIALOG_PIN_PROMPT))
        self.pin_input = QLineEdit()
        self.pin_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pin_input.textChanged.connect(
            lambda text: self.ok_button.setEnabled(bool(text.strip()))
        )
        self.content.addWidget(self.pin_input)

        self.ok_button.setText(strings.RESET_DIALOG_CONFIRM)
        self.ok_button.setObjectName("Danger")
        self.ok_button.setEnabled(False)
        self.pin_input.setFocus()

    def accept(self) -> None:
        pin = self.pin_input.text().strip()
        if not pin:
            return
        self.ok_button.setEnabled(False)
        run_api(
            lambda: self.api.factory_reset(pin),
            self._on_done,
            self._on_error,
        )

    def _on_done(self, _result: object) -> None:
        self.reset_done = True
        super().accept()

    def _on_error(self, err) -> None:
        self.ok_button.setEnabled(True)
        show_error(self, err.message)
        self.pin_input.selectAll()
        self.pin_input.setFocus()


class BackupRestoreDialog(ModalDialog):
    """PIN confirmation to restore a backup — destructive, needs typed PIN."""

    def __init__(self, api, zip_path: str, parent=None) -> None:
        super().__init__(strings.BACKUP_RESTORE_TITLE, parent)
        self.api = api
        self.zip_path = zip_path
        self.restore_done = False

        warning = QLabel(strings.BACKUP_RESTORE_CONFIRM)
        warning.setObjectName("FieldError")
        warning.setWordWrap(True)
        self.content.addWidget(warning)

        self.pin_input = QLineEdit()
        self.pin_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pin_input.setPlaceholderText(strings.LOGIN_PLACEHOLDER)
        self.pin_input.textChanged.connect(
            lambda text: self.ok_button.setEnabled(bool(text.strip()))
        )
        self.content.addWidget(self.pin_input)

        self.ok_button.setText(strings.BACKUP_RESTORE)
        self.ok_button.setObjectName("Danger")
        self.ok_button.setEnabled(False)
        self.pin_input.setFocus()

    def accept(self) -> None:
        pin = self.pin_input.text().strip()
        if not pin:
            return
        self.ok_button.setEnabled(False)
        from pathlib import Path

        zip_data = Path(self.zip_path).read_bytes()
        run_api(
            lambda: self.api.restore_backup(zip_data, pin),
            self._on_done,
            self._on_error,
        )

    def _on_done(self, _result: object) -> None:
        self.restore_done = True
        super().accept()

    def _on_error(self, err) -> None:
        self.ok_button.setEnabled(True)
        show_error(self, err.message)
        self.pin_input.selectAll()
        self.pin_input.setFocus()


class ReceiptPreview(QFrame):
    """Local mock of the printed receipt — same information layout.

    Rendered as ONE monospace label rebuilt from scratch on every change:
    no widget churn, so nothing can ever overlap or leak between renders.
    """

    COLS = 32

    def __init__(self, store_name: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("ReceiptPaper")
        self.store_name = store_name
        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            SPACING["lg"], SPACING["lg"], SPACING["lg"], SPACING["lg"]
        )
        self._label = QLabel("")
        self._label.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self._label)

    def render_preview(
        self,
        shop_name: str,
        phone: str,
        address: str,
        footer: str,
        show_credit: bool,
    ) -> None:
        width = self.COLS
        from ui.i18n import current_language

        def fit(text: str) -> str:
            return text if len(text) <= width else text[: width - 1] + "…"

        def center(text: str) -> str:
            return fit(text).center(width).rstrip()

        def row(left: str, right: str) -> str:
            space = width - len(right)
            if current_language == "ar":
                return fit(right).ljust(len(right) + 1) + fit(left).rjust(
                    width - len(right) - 1
                )
            return fit(left)[:space].ljust(space) + right

        lines = [center(shop_name or self.store_name)]
        if phone:
            lines.append(center(f"Tél : {phone}"))
        if address:
            lines.append(center(address))
        lines.append(center(datetime.now().strftime("Le %d/%m/%Y %H:%M")))
        lines.append(center(strings.SETTINGS_PREVIEW_TICKET))
        lines.append("-" * width)
        lines.append(fit(strings.SETTINGS_PREVIEW_SAMPLE_PRODUCT))
        lines.append(row("  2 x 40.00", "80.00"))
        lines.append("-" * width)
        lines.append(row(strings.SETTINGS_PREVIEW_TOTAL, "80.00"))
        if show_credit:
            lines.append(fit(strings.SETTINGS_PREVIEW_CUSTOMER))
            lines.append(row(strings.SETTINGS_PREVIEW_PAID, "30.00"))
            lines.append(row(strings.SETTINGS_PREVIEW_REMAINING, "50.00"))
        lines.append("")
        lines.append(center(footer or strings.SETTINGS_PREVIEW_DEFAULT_FOOTER))
        self._label.setText("\n".join(lines))
