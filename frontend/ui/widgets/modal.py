from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from ui import strings
from ui.styles.tokens import SPACING


class ModalDialog(QDialog):
    """Base for every dialog: title, content layout, Save/Cancel buttons.

    Subclasses fill self.content and override accept() for validation.
    """

    def __init__(self, title: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(420)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(
            SPACING["xl"], SPACING["xl"], SPACING["xl"], SPACING["lg"]
        )
        outer.setSpacing(SPACING["md"])

        heading = QLabel(title)
        heading.setObjectName("ScreenTitle")
        outer.addWidget(heading)

        self.content = QVBoxLayout()
        self.content.setSpacing(SPACING["md"])
        outer.addLayout(self.content, stretch=1)

        self.buttons = QDialogButtonBox()
        self.ok_button = QPushButton(strings.SAVE)
        self.ok_button.setObjectName("Primary")
        self.cancel_button = QPushButton(strings.CANCEL)
        self.buttons.addButton(self.ok_button, QDialogButtonBox.ButtonRole.AcceptRole)
        self.buttons.addButton(
            self.cancel_button, QDialogButtonBox.ButtonRole.RejectRole
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        outer.addWidget(self.buttons)


def show_error(parent, message: str, title: str = "") -> None:
    QMessageBox.critical(parent, title or strings.ERROR_TITLE, message)


def show_info(parent, message: str, title: str = "") -> None:
    QMessageBox.information(parent, title or strings.INFO_TITLE, message)


def ask_confirm(parent, message: str) -> bool:
    result = QMessageBox.question(
        parent,
        strings.CONFIRM_TITLE,
        message,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
    )
    return result == QMessageBox.StandardButton.Yes
