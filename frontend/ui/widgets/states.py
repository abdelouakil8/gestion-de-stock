"""Section states — every data section visibly loads and has a designed
empty state instead of a blank widget or a frozen window.

StatefulStack wraps a content widget with two extra pages:
  loading  -> animated "Chargement…" dots (QTimer, no GPU)
  empty    -> icon + French sentence + optional primary action
"""

from collections.abc import Callable

import qtawesome as qta
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ui import strings
from ui.styles.tokens import NEUTRAL, SPACING


class LoadingDots(QLabel):
    """'Chargement' with animated trailing dots — cheap and visible."""

    def __init__(self, parent=None) -> None:
        super().__init__(strings.LOADING, parent)
        self.setObjectName("LoadingDots")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._step = 0
        self._timer = QTimer(self)
        self._timer.setInterval(350)
        self._timer.timeout.connect(self._tick)

    def _tick(self) -> None:
        self._step = (self._step + 1) % 4
        self.setText(strings.LOADING + "." * self._step)

    def showEvent(self, event) -> None:
        self._timer.start()
        super().showEvent(event)

    def hideEvent(self, event) -> None:
        self._timer.stop()
        super().hideEvent(event)


class EmptyState(QWidget):
    """Icon + title + hint + optional call-to-action, centered."""

    def __init__(
        self,
        icon: str,
        title: str,
        hint: str = "",
        action_label: str = "",
        on_action: Callable[[], None] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("EmptyState")
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(SPACING["sm"])

        icon_label = QLabel()
        icon_label.setPixmap(qta.icon(icon, color=NEUTRAL["400"]).pixmap(44, 44))
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setStyleSheet("background: transparent;")
        layout.addWidget(icon_label)

        title_label = QLabel(title)
        title_label.setObjectName("EmptyStateText")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

        if hint:
            hint_label = QLabel(hint)
            hint_label.setObjectName("Muted")
            hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            hint_label.setWordWrap(True)
            layout.addWidget(hint_label)

        if action_label and on_action is not None:
            button = QPushButton(action_label)
            button.setObjectName("Primary")
            button.clicked.connect(on_action)
            layout.addWidget(button, alignment=Qt.AlignmentFlag.AlignCenter)


class StatefulStack(QStackedWidget):
    """loading / empty / content pages for one data section."""

    def __init__(self, content: QWidget, empty: EmptyState, parent=None) -> None:
        super().__init__(parent)
        self._loading = LoadingDots()
        self._empty = empty
        self._content = content
        self.addWidget(self._loading)
        self.addWidget(self._empty)
        self.addWidget(self._content)
        self.show_loading()

    def show_loading(self) -> None:
        self.setCurrentWidget(self._loading)

    def show_empty(self) -> None:
        self.setCurrentWidget(self._empty)

    def show_content(self) -> None:
        self.setCurrentWidget(self._content)
