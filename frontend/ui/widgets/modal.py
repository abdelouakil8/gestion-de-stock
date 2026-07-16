from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
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
        self.setMinimumWidth(460)
        self._adjusting = False
        # Paint the dialog's own background from the stylesheet ($background)
        # rather than the (possibly dark) OS palette — see main._apply_theme,
        # which also installs a full theme-derived QPalette as a backstop.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Dark header band — mirrors the sidebar so the dialog reads as part of
        # the app, not a stark white box. Holds the dialog title in light text.
        header = QWidget()
        header.setObjectName("DialogHeader")
        header.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(
            SPACING["xl"], SPACING["lg"], SPACING["xl"], SPACING["lg"]
        )
        heading = QLabel(title)
        heading.setObjectName("DialogTitle")
        header_layout.addWidget(heading)
        header_layout.addStretch(1)
        outer.addWidget(header)

        # Body: the scrollable content area on a soft surface.
        body = QWidget()
        body.setObjectName("DialogBody")
        body.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(
            SPACING["xl"], SPACING["lg"], SPACING["xl"], SPACING["lg"]
        )
        body_layout.setSpacing(SPACING["md"])

        holder = QWidget()
        holder.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.content = QVBoxLayout(holder)
        self.content.setContentsMargins(0, 0, 0, 0)
        self.content.setSpacing(SPACING["md"])

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setSizeAdjustPolicy(
            QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents
        )
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setWidget(holder)
        self._scroll.viewport().setAttribute(
            Qt.WidgetAttribute.WA_StyledBackground, True
        )
        body_layout.addWidget(self._scroll, stretch=1)

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
        
        # Explicitly connect the buttons to bypass QDialogButtonBox routing quirks
        # when extra buttons with different roles are added by subclasses.
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
        body_layout.addWidget(self.buttons)
        outer.addWidget(body)

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
        the new content. Pin the viewport height to the holder's own size
        hint (both directions: the dialog can GROW and SHRINK back), clamped
        so the dialog never exceeds ~95 % of the screen (past which the
        scroll bar correctly takes over) — then re-center, so the dialog
        expands from its middle instead of dropping below the taskbar.
        """
        if self._adjusting:
            return
        self._adjusting = True
        try:
            holder = self._scroll.widget()
            if holder is None:
                return

            # 1. Measure chrome (header + buttons + margins) BEFORE touching anything.
            # This overhead is stable across resizes.
            chrome = max(0, self.height() - self._scroll.height())

            # 2. Clear any fixed-height constraint on the scroll area so the dialog
            # is allowed to shrink when switching back to a smaller view.
            self._scroll.setMinimumHeight(0)
            self._scroll.setMaximumHeight(16777215)  # QWIDGETSIZE_MAX

            # 3. Flush pending layout changes so sizeHint() reflects newly shown/hidden items.
            QApplication.processEvents()
            holder.adjustSize()

            screen = self.screen() or QApplication.primaryScreen()
            cap = int(screen.availableGeometry().height() * 0.95) if screen else 800
            hint = holder.sizeHint().height()
            layout = holder.layout()
            if layout is not None and layout.hasHeightForWidth():
                # Word-wrapped labels under-report in sizeHint(); ask the layout
                # for the real height at the current viewport width instead.
                hint = max(hint, layout.heightForWidth(self._scroll.viewport().width()))

            target = min(hint + 2, max(160, cap - chrome))

            # 4. Explicitly resize the dialog. adjustSize() is asynchronous and
            # doesn't shrink windows reliably. By resizing explicitly, self.frameGeometry()
            # immediately reflects the new size so _keep_on_screen() centers it correctly.

            # To bypass any cached minimumSizeHint from the old layout, we force the
            # dialog to the exact new height, then release it.
            self.setFixedHeight(target + chrome)
            self.setMinimumHeight(0)
            self.setMaximumHeight(16777215)

            # Ensure the scroll area doesn't collapse below the target size.
            self._scroll.setMinimumHeight(target)

            self._keep_on_screen()
        finally:
            self._adjusting = False

    def _keep_on_screen(self) -> None:
        """Keep the whole dialog centered and on-screen after it grows."""
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
