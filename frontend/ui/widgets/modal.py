from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QApplication,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ui import strings
from ui.styles.tokens import SPACING


class ModalDialog(QDialog):
    """Base for every dialog: title, content layout, Save/Cancel buttons.

    Subclasses fill self.content and override accept() for validation.

    Screen-aware sizing: the content lives in a scroll area and the dialog
    never exceeds ~90 % of the available screen — long forms (fiche
    produit…) scroll instead of overflowing small displays.
    """

    def __init__(self, title: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(440)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(
            SPACING["xl"], SPACING["xl"], SPACING["xl"], SPACING["lg"]
        )
        outer.setSpacing(SPACING["md"])

        heading = QLabel(title)
        heading.setObjectName("ScreenTitle")
        outer.addWidget(heading)

        holder = QWidget()
        self.content = QVBoxLayout(holder)
        self.content.setContentsMargins(0, 0, SPACING["xs"], 0)
        self.content.setSpacing(SPACING["md"])

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setSizeAdjustPolicy(
            QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents
        )
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setWidget(holder)
        outer.addWidget(self._scroll, stretch=1)

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

    def showEvent(self, event) -> None:
        """Clamp to the ACTUAL screen so every display size works."""
        screen = self.screen() or QApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            self.setMaximumHeight(int(available.height() * 0.9))
            self.setMaximumWidth(int(available.width() * 0.9))
        super().showEvent(event)

    def fit_to_content(self) -> None:
        """Re-size to fit the content after it changes AFTER first layout.

        QScrollArea.sizeHint() is captured at first layout and does NOT track
        a section being shown/hidden later (a partial-payment block, an
        expanded form…), so the dialog would stay at its old height and clip
        the new content. Drive the viewport height from the holder's own size
        hint, clamped so the dialog never exceeds ~90 % of the screen (past
        which the scroll bar correctly takes over).
        """
        holder = self._scroll.widget()
        if holder is None:
            return
        holder.adjustSize()
        screen = self.screen() or QApplication.primaryScreen()
        cap = int(screen.availableGeometry().height() * 0.9) if screen else 800
        chrome = max(0, self.height() - self._scroll.height())
        target = min(holder.sizeHint().height(), max(160, cap - chrome))
        self._scroll.setMinimumHeight(target)
        self.adjustSize()
        self._keep_on_screen()

    def _keep_on_screen(self) -> None:
        """Keep the whole dialog on-screen after it grows.

        adjustSize() expands the window downward from its top-left, so
        revealing a section (the partial-payment block…) could push the
        confirm buttons under the taskbar — the operator then had to drag the
        window up to reach them. Re-center on the screen and clamp the top so
        every control stays reachable (the scroll area takes over if the
        content is taller than the screen)."""
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        frame = self.frameGeometry()
        frame.moveCenter(available.center())
        if frame.top() < available.top():
            frame.moveTop(available.top())
        self.move(frame.topLeft())


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
