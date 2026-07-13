import qtawesome as qta
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from ui import strings
from ui.styles.tokens import NEUTRAL, SPACING


class PaginationBar(QWidget):
    """Prev / "Page X / Y" / Next bar. Auto-hides on single page."""

    page_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, SPACING["xs"], 0, SPACING["xs"])
        layout.setSpacing(SPACING["sm"])
        layout.addStretch(1)

        self._prev = QPushButton(
            qta.icon("fa5s.chevron-left", color=NEUTRAL["600"]),
            strings.PAGINATION_PREV,
        )
        self._prev.clicked.connect(lambda: self._go(self._page - 1))
        layout.addWidget(self._prev)

        self._label = QLabel()
        layout.addWidget(self._label)

        self._next = QPushButton(
            qta.icon("fa5s.chevron-right", color=NEUTRAL["600"]),
            strings.PAGINATION_NEXT,
        )
        self._next.clicked.connect(lambda: self._go(self._page + 1))
        layout.addWidget(self._next)

        layout.addStretch(1)
        self._page = 0
        self._total = 1
        self.set_state(0, 1)

    def set_state(self, page: int, total_pages: int) -> None:
        self._page = page
        self._total = max(1, total_pages)
        self._prev.setEnabled(page > 0)
        self._next.setEnabled(page < self._total - 1)
        self._label.setText(
            strings.PAGINATION_PAGE.format(current=page + 1, total=self._total)
        )
        self.setVisible(self._total > 1)

    def _go(self, page: int) -> None:
        if 0 <= page < self._total:
            self.set_state(page, self._total)
            self.page_changed.emit(page)
