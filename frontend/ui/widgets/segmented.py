"""Segmented control — the 3-state price-level selector (Détail / Gros /
Super gros). Pure QPushButtons in an exclusive group; the server resolves
the actual price, this widget only reports the chosen level."""

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QPushButton, QWidget

from ui import strings

LEVELS = ["detail", "gros", "super_gros"]


class PriceLevelSelector(QWidget):
    def __init__(
        self,
        on_change: Callable[[str], None] | None = None,
        level: str = "detail",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._on_change = on_change
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, QPushButton] = {}
        for value in LEVELS:
            button = QPushButton(strings.PRICE_LEVEL_LABELS[value])
            button.setObjectName("Segment")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            self._group.addButton(button)
            layout.addWidget(button)
            self._buttons[value] = button
            button.toggled.connect(
                lambda checked, v=value: self._emit(v) if checked else None
            )
        self._initializing = True
        self.set_level(level)
        self._initializing = False

    def _emit(self, level: str) -> None:
        if self._on_change is not None and not self._initializing:
            self._on_change(level)

    def level(self) -> str:
        for value, button in self._buttons.items():
            if button.isChecked():
                return value
        return "detail"

    def set_level(self, level: str) -> None:
        button = self._buttons.get(level, self._buttons["detail"])
        button.setChecked(True)
