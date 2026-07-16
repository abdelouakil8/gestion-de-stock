"""KPI card, rank bars, rule card, and date picker for the statistics screen."""

from decimal import Decimal

import qtawesome as qta
from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QCalendarWidget,
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ui import strings
from ui.styles.tokens import ICON_SIZES, SPACING
from ui.widgets.badge import DeltaChip
from ui.widgets.card import Card
from ui.widgets.modal import ModalDialog

_KPI_BLUE = ("#2563EB", "primary")
_KPI_GREEN = ("#16A34A", "success")
_KPI_VIOLET = ("#7C3AED", "violet")
_KPI_AMBER = ("#D97706", "warning")
_KPI_RED = ("#DC2626", "danger")

_CAT_PALETTE = ["#2563EB", "#16A34A", "#D97706", "#7C3AED", "#0D9488", "#DB2777"]


class KpiCard(Card):
    """Headline metric: colored icon chip + caption, big value, and an
    insight line that can carry a comparison chip (delta vs previous)."""

    def __init__(
        self, caption, icon, color, kpi_type, show_delta=False, parent=None
    ) -> None:
        super().__init__(parent)
        top = QHBoxLayout()
        top.setSpacing(SPACING["sm"])
        chip = QLabel()
        chip.setFixedSize(40, 40)
        chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        chip.setPixmap(
            qta.icon(icon, color=color).pixmap(ICON_SIZES["lg"], ICON_SIZES["lg"])
        )
        chip.setObjectName("KpiChip")
        chip.setProperty("kpi", kpi_type)
        top.addWidget(chip)
        caption_label = QLabel(caption)
        caption_label.setObjectName("StatCardTitle")
        caption_label.setWordWrap(True)
        top.addWidget(caption_label, 1)
        self.body.addLayout(top)

        self.value = QLabel("—")
        self.value.setObjectName("StatCardValue")
        self.value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.body.addWidget(self.value)

        row2 = QHBoxLayout()
        row2.setSpacing(SPACING["sm"])
        self.delta = DeltaChip() if show_delta else None
        if self.delta is not None:
            self.delta.setToolTip(strings.STATS_VS_PREVIOUS)
            row2.addWidget(self.delta, 0, Qt.AlignmentFlag.AlignVCenter)
        self.sub = QLabel("")
        self.sub.setObjectName("Muted")
        self.sub.setVisible(False)
        row2.addWidget(self.sub, 1, Qt.AlignmentFlag.AlignVCenter)
        self.body.addLayout(row2)
        self.body.addStretch(1)

    def set_value(self, text: str, sub: str = "", tone: str = "") -> None:
        self.value.setText(text)
        self.value.setProperty("tone", tone)
        self.value.style().unpolish(self.value)
        self.value.style().polish(self.value)
        if sub:
            self.sub.setText(sub)
            self.sub.setVisible(True)
        else:
            self.sub.setVisible(False)

    def set_delta(self, current: Decimal, previous: Decimal) -> None:
        if self.delta is not None:
            self.delta.set_delta(current, previous)


class RankBars(QWidget):
    """A list of labelled horizontal bars (category profitability / share)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(SPACING["sm"])
        self._empty = QLabel(strings.STATS_NO_DATA)
        self._empty.setObjectName("Muted")
        self._layout.addWidget(self._empty)
        self._layout.addStretch(1)

    def _clear(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def set_rows(self, rows) -> None:
        self._clear()
        if not rows:
            self._empty = QLabel(strings.STATS_NO_DATA)
            self._empty.setObjectName("Muted")
            self._layout.addWidget(self._empty)
            self._layout.addStretch(1)
            return
        for label, value_text, ratio, color in rows:
            self._layout.addWidget(self._make_row(label, value_text, ratio, color))
        self._layout.addStretch(1)

    def _make_row(self, label, value_text, ratio, color) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACING["sm"])
        name = QLabel(label)
        name.setMinimumWidth(112)
        name.setStyleSheet("font-weight: 600; background: transparent;")
        layout.addWidget(name)

        track = QFrame()
        track.setFixedHeight(12)
        track.setObjectName("RankTrack")
        tl = QHBoxLayout(track)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(0)
        fill = QFrame()
        fill.setStyleSheet(f"background: {color}; border-radius: 6px;")
        clamped = max(0.0, min(1.0, ratio))
        tl.addWidget(fill, max(1, int(clamped * 1000)))
        spacer = QWidget()
        spacer.setStyleSheet("background: transparent;")
        tl.addWidget(spacer, max(0, int(round((1 - clamped) * 1000))))
        layout.addWidget(track, 1)

        value = QLabel(value_text)
        value.setObjectName("Muted")
        value.setMinimumWidth(72)
        value.setAlignment(
            Qt.AlignmentFlag.AlignTrailing | Qt.AlignmentFlag.AlignVCenter
        )
        layout.addWidget(value)
        return row


class RuleCard(QWidget):
    """Readable French association rule with its numbers."""

    def __init__(self, rule: dict, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("RuleCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            SPACING["md"], SPACING["sm"], SPACING["md"], SPACING["sm"]
        )
        layout.setSpacing(SPACING["xs"])

        antecedent = " + ".join(p["name"] for p in rule["antecedent"])
        consequent = " + ".join(p["name"] for p in rule["consequent"])
        sentence = QLabel(
            strings.STATS_ASSOCIATION_RULE.format(
                antecedent=antecedent, consequent=consequent
            )
        )
        sentence.setWordWrap(True)
        sentence.setStyleSheet("font-weight: 600; background: transparent;")
        layout.addWidget(sentence)

        detail = QLabel(
            strings.STATS_ASSOCIATION_DETAIL.format(
                confidence=f"{rule['confidence'] * 100:.0f}",
                support=f"{rule['support'] * 100:.0f}",
                lift=f"{rule['lift']:.2f}".replace(".", ","),
            )
        )
        detail.setObjectName("Muted")
        layout.addWidget(detail)
        self.setToolTip(detail.text())


class _DailyReportDatePicker(ModalDialog):
    """A calendar picker for the end-of-day report (any past date)."""

    def __init__(self, parent=None) -> None:
        super().__init__(strings.STATS_DAILY_REPORT_TITLE, parent)
        self.selected: QDate | None = None
        prompt = QLabel(strings.STATS_DAILY_REPORT_PROMPT)
        self.content.addWidget(prompt)
        self.calendar = QCalendarWidget()
        self.calendar.setMaximumDate(QDate.currentDate())
        self.calendar.setSelectedDate(QDate.currentDate())
        self.content.addWidget(self.calendar)
        self.ok_button.setText(strings.STATS_DAILY_REPORT_GENERATE)

    def accept(self) -> None:
        self.selected = self.calendar.selectedDate()
        super().accept()
