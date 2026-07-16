"""Segmented control — the 3-state price-level selector (Détail / Gros /
Super gros). An iOS-style pill track: a sunken rounded container holds the
options, and the chosen one lights up as a filled pill. Pure QPushButtons in
an exclusive group; the server resolves the actual price, this widget only
reports the chosen level."""

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QPushButton, QWidget

from ui import strings
from ui.styles.tokens import SPACING

LEVELS = ["detail", "gros", "super_gros"]

# The optional 4th state; only present when the selector is built with
# allow_manual=True. Existing 3-state callers never see it.
MANUAL_LEVEL = "manual"


class PriceLevelSelector(QWidget):
    def __init__(
        self,
        on_change: Callable[[str], None] | None = None,
        level: str = "detail",
        parent=None,
        allow_manual: bool = False,
    ) -> None:
        super().__init__(parent)
        # The whole widget is the sunken "track"; WA_StyledBackground lets the
        # #SegmentGroup QSS background/border paint on this plain QWidget.
        self.setObjectName("SegmentGroup")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._on_change = on_change
        self._allow_manual = allow_manual
        # Instance-local level list so the module-level LEVELS constant that
        # 3-state callers rely on stays untouched.
        self._levels = list(LEVELS)
        if allow_manual:
            self._levels.append(MANUAL_LEVEL)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(
            SPACING["xs"], SPACING["xs"], SPACING["xs"], SPACING["xs"]
        )
        layout.setSpacing(SPACING["xs"])

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, QPushButton] = {}
        for value in self._levels:
            if value == MANUAL_LEVEL:
                label = strings.PRICE_LEVEL_MANUAL
            else:
                label = strings.PRICE_LEVEL_LABELS[value]
            button = QPushButton(label)
            button.setObjectName("SegmentPill")
            button.setToolTip(label)  # full label on hover if a tight cell clips
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
