"""Custom hand-drawn charts (QPainter) for the Statistics dashboard.

No chart library, no GPU effects — same conventions as bars.py: anti-aliased
vector drawing that reads the themeable accent + neutral tokens directly,
formats with the shared French helpers, and mirrors cleanly in RTL.

Two reusable widgets:
  LineChart  — dual revenue/profit series, smooth curves, gradient fill.
  DonutChart — payment-method split, hollow center, inline legend.

Both paint a small inline empty state so they never render as a blank widget
when there is no data for the selected period.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import qtawesome as qta
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QSizePolicy, QWidget

from ui import format as fmt
from ui import strings
from ui.styles import tokens

# Vibrant palette cycled by the payment-method order (matches the previous
# PaymentShareBar palette so the look stays consistent).
_PM_PALETTE = [
    "#2563EB",
    "#16A34A",
    "#D97706",
    "#7C3AED",
    "#0D9488",
    "#DB2777",
]


@dataclass
class LinePoint:
    """One day of the evolution series."""

    day: date
    revenue: Decimal
    profit: Decimal


def _scaled_font(base: QFont, delta_px: int) -> QFont:
    """Smaller/larger font derived from the app font, never negative.

    The app font is defined in PIXELS by the stylesheet so pointSizeF() is
    -1; derive the pixel size explicitly (mirrors bars.py)."""
    font = QFont(base)
    if base.pixelSize() > 0:
        font.setPixelSize(max(8, base.pixelSize() + delta_px))
    else:
        font.setPointSizeF(max(6.0, base.pointSizeF() + delta_px * 0.8))
    return font


def _compact_money(value: Decimal) -> str:
    """1 234 567,50 -> '1 234 567' for axis tick labels (no decimals).

    Keeps the French NBSP thousands separator; large amounts stay readable
    on a cramped Y-axis."""
    amount = Decimal(str(value)).quantize(Decimal("1"), rounding="ROUND_HALF_UP")
    return f"{amount:,}".replace(",", "\u202f")  # NBSP thousands


def _abbrev_money(value: Decimal) -> str:
    """Very compact amount for the cramped donut center: 2 340 500 -> '2,3 M'.

    Only millions are abbreviated; smaller amounts keep the readable
    thousands-separated form (still short enough for the hollow center)."""
    if abs(float(value)) >= 1_000_000:
        return f"{float(value) / 1_000_000:.1f}".replace(".", ",") + " M"
    return _compact_money(value)


class LineChart(QWidget):
    """Dual revenue/profit evolution line chart with gradient fill."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._points: list[LinePoint] = []
        self.setMinimumHeight(220)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        # Transparent so the host card's surface shows through.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background: transparent;")

    def set_data(self, points: list[LinePoint]) -> None:
        self._points = list(points)
        self.update()

    # ----------------------------------------------------------- rendering

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if not self._points:
            self._paint_empty(painter)
            painter.end()
            return

        self._paint_chart(painter)
        painter.end()

    def _paint_empty(self, painter: QPainter) -> None:
        """Designed empty state so the chart never looks broken."""
        painter.setPen(QColor(tokens.NEUTRAL["400"]))
        icon = qta.icon("fa5s.chart-line", color=tokens.NEUTRAL["400"])
        painter.drawPixmap(
            self.width() // 2 - 22,
            self.height() // 2 - 32,
            icon.pixmap(44, 44),
        )
        painter.setPen(QColor(tokens.NEUTRAL["500"]))
        painter.setFont(_scaled_font(self.font(), 1))
        text_rect = QRectF(0, self.height() // 2 + 16, self.width(), 24)
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            strings.STATS_CHART_EMPTY,
        )

    def _paint_chart(self, painter: QPainter) -> None:
        width = self.width()
        height = self.height()
        legend_h = 22
        pad_left = 52  # room for Y tick labels
        pad_right = 14
        pad_top = legend_h + 6
        pad_bottom = 26  # room for X date labels

        plot_w = max(10, width - pad_left - pad_right)
        plot_h = max(10, height - pad_top - pad_bottom)

        # ---- Y scale: nice rounded max across both series ----
        max_value = max(
            (max(p.revenue, p.profit) for p in self._points), default=Decimal("0")
        )
        nice_max = _nice_ceiling(float(max_value))
        if nice_max <= 0:
            nice_max = 1.0

        # ---- legend chips ----
        self._paint_legend(painter, legend_h)

        # ---- gridlines + Y ticks (5 steps) ----
        grid_color = QColor(tokens.NEUTRAL["200"])
        tick_color = QColor(tokens.NEUTRAL["500"])
        painter.setFont(_scaled_font(self.font(), -2))
        steps = 4
        for step in range(steps + 1):
            ratio = step / steps
            y = pad_top + plot_h - plot_h * ratio
            painter.drawLine(pad_left, int(y), width - pad_right, int(y))
            painter.setPen(tick_color)
            label = _compact_money(
                Decimal(str(nice_max * ratio)).quantize(Decimal("1"))
            )
            painter.drawText(
                QRectF(0, y - 9, pad_left - 6, 18),
                Qt.AlignmentFlag.AlignTrailing | Qt.AlignmentFlag.AlignVCenter,
                label,
            )
            painter.setPen(QPen(grid_color, 1))

        # ---- X positions (one per point) ----
        count = len(self._points)
        if count == 1:
            xs = [pad_left + plot_w / 2]
        else:
            xs = [pad_left + plot_w * i / (count - 1) for i in range(count)]

        def y_of(value: Decimal) -> float:
            ratio = float(value) / nice_max if nice_max > 0 else 0.0
            return pad_top + plot_h - plot_h * max(0.0, min(1.0, ratio))

        revenue_pts = [(xs[i], y_of(p.revenue)) for i, p in enumerate(self._points)]
        profit_pts = [(xs[i], y_of(p.profit)) for i, p in enumerate(self._points)]

        # RTL mirrors the drawing order so the most recent day sits on the
        # leading edge of the reading direction.
        if self.layoutDirection() == Qt.LayoutDirection.RightToLeft:
            revenue_pts.reverse()
            profit_pts.reverse()

        accent = QColor(tokens.CURRENT_ACCENT)
        profit_color = QColor(tokens.SEMANTIC["success"])

        # ---- revenue gradient fill under the line ----
        if len(revenue_pts) >= 2:
            fill_path = QPainterPath()
            fill_path.moveTo(revenue_pts[0][0], pad_top + plot_h)
            _add_smooth_curve(fill_path, revenue_pts)
            fill_path.lineTo(revenue_pts[-1][0], pad_top + plot_h)
            fill_path.closeSubpath()

            gradient = QLinearGradient(0, pad_top, 0, pad_top + plot_h)
            fill_top = QColor(accent)
            fill_top.setAlpha(70)
            fill_bottom = QColor(accent)
            fill_bottom.setAlpha(0)
            gradient.setColorAt(0.0, fill_top)
            gradient.setColorAt(1.0, fill_bottom)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(gradient)
            painter.drawPath(fill_path)

        # ---- profit line (thinner, no fill) ----
        if len(profit_pts) >= 2:
            path = QPainterPath()
            path.moveTo(*profit_pts[0])
            _add_smooth_curve(path, profit_pts)
            painter.setPen(QPen(profit_color, 2.0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)
        elif profit_pts:
            painter.setBrush(profit_color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(
                QRectF(profit_pts[0][0] - 2.5, profit_pts[0][1] - 2.5, 5, 5)
            )

        # ---- revenue line ----
        if len(revenue_pts) >= 2:
            path = QPainterPath()
            path.moveTo(*revenue_pts[0])
            _add_smooth_curve(path, revenue_pts)
            painter.setPen(QPen(accent, 2.4))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)
        elif revenue_pts:
            painter.setBrush(accent)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(
                QRectF(revenue_pts[0][0] - 2.5, revenue_pts[0][1] - 2.5, 5, 5)
            )

        # ---- X date labels (sparse so they never collide) ----
        painter.setPen(tick_color)
        painter.setFont(_scaled_font(self.font(), -2))
        label_every = max(1, (count + 6) // 7)  # ~7 labels max
        span_days = (self._points[-1].day - self._points[0].day).days
        for i in range(0, count, label_every):
            day = self._points[i].day
            if span_days <= 45:
                label = day.strftime("%d/%m")
            else:
                label = day.strftime("%m/%y")
            painter.drawText(
                QRectF(xs[i] - 28, pad_top + plot_h + 4, 56, 18),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                label,
            )

    def _paint_legend(self, painter: QPainter, height: int) -> None:
        """Two legend chips (revenue + profit) at the top of the plot."""
        painter.setFont(_scaled_font(self.font(), -2))
        accent = QColor(tokens.CURRENT_ACCENT)
        profit_color = QColor(tokens.SEMANTIC["success"])
        muted = QColor(tokens.NEUTRAL["600"])

        x = 52
        mid = height / 2
        for color, text in (
            (accent, strings.STATS_REVENUE_LEGEND),
            (profit_color, strings.STATS_PROFIT_LEGEND),
        ):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(QRectF(x, mid - 4, 9, 9))
            painter.setPen(muted)
            text_width = painter.fontMetrics().horizontalAdvance(text)
            painter.drawText(
                QRectF(x + 13, mid - 9, text_width + 4, 18),
                Qt.AlignmentFlag.AlignLeading | Qt.AlignmentFlag.AlignVCenter,
                text,
            )
            x += 13 + text_width + 18


class DonutChart(QWidget):
    """Payment-method split donut with a hollow center + inline legend."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._slices: list[tuple[str, Decimal, QColor]] = []
        self._total: Decimal = Decimal("0")
        self.setMinimumHeight(220)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background: transparent;")

    def set_items(self, items: list[tuple[str, Decimal]]) -> None:
        """Build the slice list from generic (label, amount) pairs.

        Zero/negative amounts are skipped; colors cycle the shared palette in
        the order given (so the caller controls slice colors by ordering)."""
        total = sum((Decimal(str(amount)) for _, amount in items), Decimal("0"))
        slices: list[tuple[str, Decimal, QColor]] = []
        if total > 0:
            index = 0
            for label, raw in items:
                amount = Decimal(str(raw))
                if amount <= 0:
                    continue
                color = QColor(_PM_PALETTE[index % len(_PM_PALETTE)])
                slices.append((label, amount, color))
                index += 1
        self._total = total
        self._slices = slices
        self.update()

    def set_methods(self, methods: list[dict]) -> None:
        """Build the slice list from a payment-methods API payload."""
        self.set_items(
            [
                (
                    strings.PAYMENT_METHOD_LABELS.get(
                        method["payment_method"], method["payment_method"]
                    ),
                    Decimal(str(method["total"])),
                )
                for method in methods
            ]
        )

    # ----------------------------------------------------------- rendering

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        total = getattr(self, "_total", Decimal("0"))
        slices = getattr(self, "_slices", [])
        if not slices or total <= 0:
            self._paint_empty(painter)
            painter.end()
            return

        self._paint_chart(painter, slices, total)
        painter.end()

    def _paint_empty(self, painter: QPainter) -> None:
        painter.setPen(QColor(tokens.NEUTRAL["400"]))
        icon = qta.icon("fa5s.wallet", color=tokens.NEUTRAL["400"])
        painter.drawPixmap(
            self.width() // 2 - 22,
            self.height() // 2 - 32,
            icon.pixmap(44, 44),
        )
        painter.setPen(QColor(tokens.NEUTRAL["500"]))
        painter.setFont(_scaled_font(self.font(), 1))
        painter.drawText(
            QRectF(0, self.height() // 2 + 16, self.width(), 24),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            strings.STATS_NO_DATA,
        )

    def _paint_chart(
        self,
        painter: QPainter,
        slices: list[tuple[str, Decimal, QColor]],
        total: Decimal,
    ) -> None:
        width = self.width()
        height = self.height()

        # Donut on the left half, legend on the right half.
        donut_box = min(width * 0.5, height) - 16
        donut_box = max(60, donut_box)
        donut_x = (width * 0.5 - donut_box) / 2
        donut_y = (height - donut_box) / 2
        rect = QRectF(donut_x, donut_y, donut_box, donut_box)

        # Slices: full circle, start at 12 o'clock, go clockwise.
        gap = 0.012  # radians-ish gap between slices (in turn fraction)
        start = 0.25  # 90 deg (top) in [0,1]
        for _label, amount, color in slices:
            fraction = float(amount / total)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            # drawPie uses 1/16th of a degree; 0 deg = 3 o'clock, positive = CCW.
            start_angle = int(start * 5760)
            span_angle = int(fraction * 5760 * (1 - gap / max(fraction, 1e-6)))
            painter.drawPie(rect, start_angle, -span_angle)
            start += fraction

        # Hollow center (surface-colored disc so it matches the host card in
        # both light and dark themes).
        inner = donut_box * 0.58
        center = rect.center()
        painter.setBrush(QColor(tokens.CURRENT_SURFACE))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(center, inner / 2, inner / 2)

        # Center text: total amount + caption.
        painter.setPen(QColor(tokens.NEUTRAL["900"]))
        painter.setFont(_scaled_font(self.font(), 4))
        amount_text = _abbrev_money(total)
        painter.drawText(
            QRectF(center.x() - inner / 2, center.y() - inner / 2, inner, inner * 0.6),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
            amount_text,
        )
        painter.setPen(QColor(tokens.NEUTRAL["500"]))
        painter.setFont(_scaled_font(self.font(), -2))
        painter.drawText(
            QRectF(center.x() - inner / 2, center.y(), inner, inner * 0.4),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            strings.STATS_DONUT_TOTAL,
        )

        # Legend on the right half.
        self._paint_legend(painter, width * 0.5, 0, width * 0.5, height, slices, total)

    def _paint_legend(
        self,
        painter: QPainter,
        x: float,
        y: float,
        w: float,
        h: float,
        slices: list[tuple[str, Decimal, QColor]],
        total: Decimal,
    ) -> None:
        if not slices:
            return
        row_h = min(30, h / max(len(slices), 1))
        start_y = y + (h - row_h * len(slices)) / 2
        name_font = _scaled_font(self.font(), 0)
        value_font = _scaled_font(self.font(), 0)
        muted = QColor(tokens.NEUTRAL["500"])
        text_color = QColor(tokens.NEUTRAL["800"])

        painter.setFont(name_font)
        for index, (label, amount, color) in enumerate(slices):
            row_y = start_y + index * row_h
            cy = row_y + row_h / 2
            # Color dot.
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(QRectF(x + 4, cy - 5, 10, 10))
            # Name.
            painter.setPen(text_color)
            painter.drawText(
                QRectF(x + 22, row_y, w * 0.58, row_h),
                Qt.AlignmentFlag.AlignLeading | Qt.AlignmentFlag.AlignVCenter,
                label,
            )
            # Percentage on the trailing edge (the exact amount lives in the
            # exports; crowding both here overflows the narrow legend column).
            share = float(amount / total) if total > 0 else 0.0
            painter.setPen(muted)
            painter.setFont(value_font)
            painter.drawText(
                QRectF(x + w * 0.58, row_y, w * 0.40, row_h),
                Qt.AlignmentFlag.AlignTrailing | Qt.AlignmentFlag.AlignVCenter,
                fmt.fmt_percent(share),
            )


class ColumnChart(QWidget):
    """Vertical column chart for busy-hours / weekday distributions.

    Slim bars over a subtle track; the tallest column is emphasised and its
    value labelled above it. X labels are drawn sparsely so 24 hourly columns
    never collide. Mirrors in RTL by reversing the column order."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._bars: list[tuple[str, float]] = []
        self._peak_text = ""
        self.setMinimumHeight(180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background: transparent;")

    def set_data(self, bars: list[tuple[str, float]], peak_text: str = "") -> None:
        self._bars = list(bars)
        self._peak_text = peak_text
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        values = [value for _, value in self._bars]
        if not self._bars or max(values, default=0.0) <= 0:
            self._paint_empty(painter)
            painter.end()
            return
        self._paint_chart(painter)
        painter.end()

    def _paint_empty(self, painter: QPainter) -> None:
        painter.setPen(QColor(tokens.NEUTRAL["400"]))
        icon = qta.icon("fa5s.clock", color=tokens.NEUTRAL["400"])
        painter.drawPixmap(
            self.width() // 2 - 22, self.height() // 2 - 32, icon.pixmap(44, 44)
        )
        painter.setPen(QColor(tokens.NEUTRAL["500"]))
        painter.setFont(_scaled_font(self.font(), 1))
        painter.drawText(
            QRectF(0, self.height() // 2 + 16, self.width(), 24),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            strings.STATS_NO_DATA,
        )

    def _paint_chart(self, painter: QPainter) -> None:
        width, height = self.width(), self.height()
        top_pad, label_h = 22, 20  # room for the peak label / x labels
        plot_h = max(10, height - top_pad - label_h)
        count = len(self._bars)
        gap = 6 if count > 12 else 12
        bar_w = max(4, (width - gap * (count + 1)) // count)
        total_w = count * bar_w + (count - 1) * gap
        start_x = max(gap, (width - total_w) // 2)

        values = [value for _, value in self._bars]
        maximum = max(values)
        peak_index = values.index(maximum)

        accent = QColor(tokens.CURRENT_ACCENT)
        accent_strong = QColor(tokens.darken(tokens.CURRENT_ACCENT, 0.18))
        track = QColor(tokens.NEUTRAL["200"])
        text_color = QColor(tokens.NEUTRAL["500"])

        entries = list(enumerate(self._bars))
        if self.layoutDirection() == Qt.LayoutDirection.RightToLeft:
            entries.reverse()
        label_every = 1 if count <= 8 else max(1, (count + 7) // 8)

        small = _scaled_font(self.font(), -3)
        for position, (index, (label, value)) in enumerate(entries):
            x = start_x + position * (bar_w + gap)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(track)
            painter.drawRoundedRect(QRectF(x, top_pad, bar_w, plot_h), 3, 3)
            if value > 0:
                bar_h = max(3.0, plot_h * (value / maximum))
                painter.setBrush(accent_strong if index == peak_index else accent)
                painter.drawRoundedRect(
                    QRectF(x, top_pad + plot_h - bar_h, bar_w, bar_h), 3, 3
                )
            if index == peak_index and self._peak_text:
                painter.setPen(accent_strong)
                painter.setFont(_scaled_font(self.font(), -1))
                painter.drawText(
                    QRectF(x - gap * 2, 0, bar_w + gap * 4, top_pad - 2),
                    Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                    self._peak_text,
                )
            if index % label_every == 0:
                painter.setPen(text_color)
                painter.setFont(small)
                painter.drawText(
                    QRectF(x - gap / 2, top_pad + plot_h + 2, bar_w + gap, label_h),
                    Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                    label,
                )


class GroupedBarChart(QWidget):
    """Two-series grouped bars per category — used for period comparison.

    Series A uses the theme accent, series B a fixed violet, with a small
    legend. Mirrors in RTL by reversing the category order."""

    _COLOR_B = "#7C3AED"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._labels: list[str] = []
        self._series_a: list[float] = []
        self._series_b: list[float] = []
        self._name_a = "A"
        self._name_b = "B"
        self.setMinimumHeight(200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background: transparent;")

    def set_data(
        self,
        labels: list[str],
        series_a: list[float],
        series_b: list[float],
        name_a: str = "A",
        name_b: str = "B",
    ) -> None:
        self._labels = list(labels)
        self._series_a = list(series_a)
        self._series_b = list(series_b)
        self._name_a = name_a
        self._name_b = name_b
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        maximum = max([*self._series_a, *self._series_b], default=0.0)
        if not self._labels or maximum <= 0:
            painter.setPen(QColor(tokens.NEUTRAL["500"]))
            painter.setFont(_scaled_font(self.font(), 1))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                strings.STATS_NO_DATA,
            )
            painter.end()
            return

        width, height = self.width(), self.height()
        legend_h, label_h, top_pad = 22, 18, 8
        plot_h = max(10, height - legend_h - label_h - top_pad)
        plot_top = legend_h + top_pad
        accent = QColor(tokens.CURRENT_ACCENT)
        color_b = QColor(self._COLOR_B)

        # Legend.
        painter.setFont(_scaled_font(self.font(), -2))
        painter.setBrush(accent)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(QRectF(8, 6, 12, 12), 2, 2)
        painter.setPen(QColor(tokens.NEUTRAL["600"]))
        painter.drawText(
            QRectF(24, 4, 160, 16), Qt.AlignmentFlag.AlignVCenter, self._name_a
        )
        painter.setBrush(color_b)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(QRectF(196, 6, 12, 12), 2, 2)
        painter.setPen(QColor(tokens.NEUTRAL["600"]))
        painter.drawText(
            QRectF(212, 4, 160, 16), Qt.AlignmentFlag.AlignVCenter, self._name_b
        )

        count = len(self._labels)
        group_gap = 10
        group_w = max(8, (width - group_gap * (count + 1)) // max(count, 1))
        bar_w = max(3, (group_w - 3) // 2)
        total_w = count * group_w + (count - 1) * group_gap
        start_x = max(group_gap, (width - total_w) // 2)
        text_color = QColor(tokens.NEUTRAL["500"])

        order = list(range(count))
        if self.layoutDirection() == Qt.LayoutDirection.RightToLeft:
            order.reverse()
        label_every = 1 if count <= 8 else max(1, (count + 7) // 8)
        small = _scaled_font(self.font(), -3)

        for position, index in enumerate(order):
            gx = start_x + position * (group_w + group_gap)
            for offset, (series, color) in enumerate(
                ((self._series_a, accent), (self._series_b, color_b))
            ):
                value = series[index] if index < len(series) else 0.0
                bar_h = max(2.0, plot_h * (value / maximum)) if value > 0 else 0.0
                bx = gx + offset * (bar_w + 3)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(color)
                if bar_h > 0:
                    painter.drawRoundedRect(
                        QRectF(bx, plot_top + plot_h - bar_h, bar_w, bar_h), 2, 2
                    )
            if position % label_every == 0:
                painter.setPen(text_color)
                painter.setFont(small)
                painter.drawText(
                    QRectF(
                        gx - group_gap / 2,
                        plot_top + plot_h + 2,
                        group_w + group_gap,
                        label_h,
                    ),
                    Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                    self._labels[index],
                )
        painter.end()


# -------------------------------------------------------------- helpers


def _add_smooth_curve(path: QPainterPath, points: list[tuple[float, float]]) -> None:
    """Append a smooth (catmull-rom-ish) curve through `points` to `path`.

    Cheap, dependency-free smoothing: each segment uses a cubic Bezier whose
    control points are derived from the neighbours, giving a continuous,
    natural-looking line without overshoot on sharp changes."""
    if len(points) < 2:
        return
    tension = 0.18
    for i in range(len(points) - 1):
        p0 = points[i - 1] if i > 0 else points[i]
        p1 = points[i]
        p2 = points[i + 1]
        p3 = points[i + 2] if i + 2 < len(points) else points[i + 1]

        c1x = p1[0] + (p2[0] - p0[0]) * tension
        c1y = p1[1] + (p2[1] - p0[1]) * tension
        c2x = p2[0] - (p3[0] - p1[0]) * tension
        c2y = p2[1] - (p3[1] - p1[1]) * tension
        path.cubicTo(c1x, c1y, c2x, c2y, p2[0], p2[1])


def _nice_ceiling(value: float) -> float:
    """Round up to a 'nice' axis ceiling (1, 2, 2.5, 5 × 10^n)."""
    if value <= 0:
        return 1.0
    magnitude = 10 ** (len(str(int(value))) - 1)
    normalized = value / magnitude
    for step in (1.0, 2.0, 2.5, 5.0, 10.0):
        if normalized <= step:
            return step * magnitude
    return float(magnitude * 10)
