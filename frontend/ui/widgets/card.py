import qtawesome as qta
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from ui.styles.tokens import ICON_SIZES, NEUTRAL, SPACING


class Card(QFrame):
    """Surface container with border + radius (styled via #Card in QSS)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(
            SPACING["lg"], SPACING["lg"], SPACING["lg"], SPACING["lg"]
        )
        self.body.setSpacing(SPACING["sm"])


class SectionCard(Card):
    """Card with a titled header row (icon + section title + trailing slot)."""

    def __init__(self, title: str, icon: str | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("SectionCard")
        self.header = QHBoxLayout()
        self.header.setSpacing(SPACING["sm"])
        if icon:
            icon_label = QLabel()
            icon_label.setPixmap(
                qta.icon(icon, color=NEUTRAL["500"]).pixmap(
                    ICON_SIZES["md"], ICON_SIZES["md"]
                )
            )
            icon_label.setStyleSheet("background: transparent;")
            self.header.addWidget(icon_label)
        title_label = QLabel(title)
        title_label.setObjectName("SectionTitle")
        self.header.addWidget(title_label)
        self.header.addStretch(1)
        self.body.addLayout(self.header)


class StatCard(Card):
    """Metric card: small caption title, big value, optional footer slot."""

    def __init__(self, title: str, icon: str | None = None, parent=None) -> None:
        super().__init__(parent)
        top = QHBoxLayout()
        top.setSpacing(SPACING["sm"])
        self._title = QLabel(title.upper())
        self._title.setObjectName("StatCardTitle")
        top.addWidget(self._title)
        top.addStretch(1)
        if icon:
            icon_label = QLabel()
            icon_label.setPixmap(
                qta.icon(icon, color=NEUTRAL["400"]).pixmap(
                    ICON_SIZES["md"], ICON_SIZES["md"]
                )
            )
            icon_label.setStyleSheet("background: transparent;")
            top.addWidget(icon_label)
        self.body.addLayout(top)

        self._value = QLabel("—")
        self._value.setObjectName("StatCardValue")
        self._value.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.body.addWidget(self._value)

    def set_value(self, text: str, tone: str = "") -> None:
        """Update the metric. `tone` ('danger' | 'success' | '') colors the
        value via the QSS [tone=…] variants — used e.g. to make a non-zero
        outstanding balance impossible to miss."""
        self._value.setText(text)
        self._value.setProperty("tone", tone)
        self._value.style().unpolish(self._value)
        self._value.style().polish(self._value)
