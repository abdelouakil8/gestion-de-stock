"""Badge / chip — small semantic labels (stock alerts, price levels,
credit status) and the delta chip used by statistics comparisons."""

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

# kind ∈ success | warning | danger | accent | neutral (styled in app.qss)


class Badge(QLabel):
    def __init__(self, text: str = "", kind: str = "neutral", parent=None) -> None:
        super().__init__(text, parent)
        self.setObjectName("Badge")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.set_kind(kind)

    def set_kind(self, kind: str) -> None:
        self.setProperty("kind", kind)
        # Re-polish so the property-driven QSS variant applies immediately.
        self.style().unpolish(self)
        self.style().polish(self)


class DeltaChip(Badge):
    """Comparison chip: ▲ +12 % (green) / ▼ −8 % (red) / — (neutral)."""

    def set_delta(self, current: Decimal, previous: Decimal) -> None:
        if previous == 0:
            if current > 0:
                self.setText("▲ nouveau")
                self.set_kind("success")
            else:
                self.setText("—")
                self.set_kind("neutral")
            return
        change = (current - previous) / previous
        percent = f"{abs(change) * 100:.0f}"
        if change > 0:
            self.setText(f"▲ +{percent} %")
            self.set_kind("success")
        elif change < 0:
            self.setText(f"▼ −{percent} %")
            self.set_kind("danger")
        else:
            self.setText("＝")
            self.set_kind("neutral")
