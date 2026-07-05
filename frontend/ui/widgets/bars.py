"""Hand-drawn bar chart (QPainter) — no chart library, no GPU effects.

Used by the product detail view for per-period revenue. Mirrors in RTL by
reversing the drawing order when the widget's layout direction is RTL.
"""

from decimal import Decimal

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QSizePolicy, QWidget

from ui import format as fmt
from ui.styles import tokens


class BarChart(QWidget):
    """Vertical bars with labels under and values above."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._data: list[tuple[str, Decimal]] = []
        self.setMinimumHeight(150)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_data(self, data: list[tuple[str, Decimal]]) -> None:
        self._data = list(data)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().paintEvent(event)
        if not self._data:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        width, height = self.width(), self.height()
        label_h, value_h = 20, 18
        chart_h = max(10, height - label_h - value_h)
        count = len(self._data)
        gap = 14
        bar_w = max(18, min(64, (width - gap * (count + 1)) // max(count, 1)))
        total_w = count * bar_w + (count - 1) * gap
        start_x = max(0, (width - total_w) // 2)

        maximum = max((value for _, value in self._data), default=Decimal("0"))
        accent = QColor(tokens.CURRENT_ACCENT)
        track = QColor(tokens.NEUTRAL["200"])
        text_color = QColor(tokens.NEUTRAL["600"])

        entries = list(self._data)
        if self.layoutDirection() == Qt.LayoutDirection.RightToLeft:
            entries.reverse()

        # The app font is defined in PIXELS by the stylesheet, so pointSizeF()
        # is -1 here; derive the smaller label font from pixelSize to stay
        # consistent (and never feed a non-positive size to QFont).
        small = QFont(self.font())
        if self.font().pixelSize() > 0:
            small.setPixelSize(max(9, self.font().pixelSize() - 2))
        else:
            small.setPointSizeF(max(7.0, self.font().pointSizeF() - 1.5))

        for index, (label, value) in enumerate(entries):
            x = start_x + index * (bar_w + gap)
            # Track (full height, subtle) then the value bar on top.
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(track)
            painter.drawRoundedRect(QRectF(x, value_h, bar_w, chart_h), 4, 4)
            if maximum > 0 and value > 0:
                ratio = float(value / maximum)
                bar_h = max(4.0, chart_h * ratio)
                painter.setBrush(accent)
                painter.drawRoundedRect(
                    QRectF(x, value_h + chart_h - bar_h, bar_w, bar_h), 4, 4
                )
            painter.setPen(text_color)
            painter.setFont(small)
            painter.drawText(
                QRectF(x - gap / 2, value_h + chart_h + 2, bar_w + gap, label_h),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                label,
            )
            painter.drawText(
                QRectF(x - gap, 0, bar_w + 2 * gap, value_h),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
                fmt.fmt_money(value),
            )
        painter.end()
