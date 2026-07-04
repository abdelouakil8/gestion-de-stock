"""Non-blocking toasts — success/info feedback without stealing focus.

Modal dialogs remain for confirmations and errors that require a decision;
everything that just says "ça a marché" goes through show_toast(). One
toast at a time, auto-dismissed, repositioned on window resize. No
animations (low-spec target) — appear/disappear is instant.
"""

import qtawesome as qta
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from ui.styles.tokens import ICON_SIZES, SPACING

_ICONS = {"success": "fa5s.check-circle", "error": "fa5s.exclamation-circle"}


class _Toast(QWidget):
    def __init__(self, window: QWidget, message: str, kind: str) -> None:
        super().__init__(window)
        self.setObjectName("Toast")
        self.setProperty("kind", kind)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        # QWidget subclass: required for the QSS background to paint.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(
            SPACING["lg"], SPACING["sm"], SPACING["lg"], SPACING["sm"]
        )
        layout.setSpacing(SPACING["sm"])
        icon = QLabel()
        icon.setPixmap(
            qta.icon(_ICONS.get(kind, _ICONS["success"]), color="white").pixmap(
                ICON_SIZES["md"], ICON_SIZES["md"]
            )
        )
        icon.setStyleSheet("background: transparent;")
        layout.addWidget(icon)
        layout.addWidget(QLabel(message))

        self.adjustSize()
        self.reposition()
        self.show()
        self.raise_()
        QTimer.singleShot(2600, self._dismiss)

    def reposition(self) -> None:
        parent = self.parentWidget()
        if parent is not None:
            self.move((parent.width() - self.width()) // 2, SPACING["xl"] + 40)

    def _dismiss(self) -> None:
        window = self.window()
        if getattr(window, "_active_toast", None) is self:
            window._active_toast = None
        self.deleteLater()


def show_toast(anywidget: QWidget, message: str, kind: str = "success") -> None:
    """Show a toast on the top-level window of `anywidget`."""
    window = anywidget.window()
    previous = getattr(window, "_active_toast", None)
    if previous is not None:
        previous._dismiss()
    window._active_toast = _Toast(window, message, kind)
