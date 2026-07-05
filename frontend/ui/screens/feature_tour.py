"""Feature tour dialog (In-App Help)."""

import qtawesome as qta
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QScrollArea,
)

from ui import strings
from ui.styles import tokens
from ui.styles.tokens import SPACING


class FeatureTourDialog(QDialog):
    """A simple dialog to introduce the application's features."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(strings.FEATURE_TOUR_TITLE)
        self.setMinimumWidth(600)
        self.setMinimumHeight(500)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(*[SPACING["xl"]] * 4)
        layout.setSpacing(SPACING["lg"])

        title = QLabel(strings.FEATURE_TOUR_WELCOME)
        title.setObjectName("ScreenTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        
        container = QWidget()
        features_layout = QVBoxLayout(container)
        features_layout.setSpacing(SPACING["md"])
        
        def add_feature(icon_name: str, name: str, desc: str) -> None:
            row = QHBoxLayout()
            row.setSpacing(SPACING["md"])
            
            icon = QLabel()
            icon.setPixmap(qta.icon(icon_name, color=tokens.CURRENT_ACCENT).pixmap(32, 32))
            icon.setAlignment(Qt.AlignmentFlag.AlignTop)
            row.addWidget(icon)
            
            text_layout = QVBoxLayout()
            text_layout.setSpacing(SPACING["xs"])
            
            title_lbl = QLabel(name)
            title_lbl.setStyleSheet("font-weight: bold;")
            text_layout.addWidget(title_lbl)
            
            desc_lbl = QLabel(desc)
            desc_lbl.setWordWrap(True)
            desc_lbl.setObjectName("Muted")
            text_layout.addWidget(desc_lbl)
            
            row.addLayout(text_layout)
            row.addStretch(1)
            features_layout.addLayout(row)

        add_feature("fa5s.cash-register", strings.FEATURE_TOUR_CHECKOUT_TITLE, strings.FEATURE_TOUR_CHECKOUT_DESC)
        add_feature("fa5s.boxes", strings.FEATURE_TOUR_INVENTORY_TITLE, strings.FEATURE_TOUR_INVENTORY_DESC)
        add_feature("fa5s.chart-line", strings.FEATURE_TOUR_STATS_TITLE, strings.FEATURE_TOUR_STATS_DESC)
        add_feature("fa5s.bell", strings.FEATURE_TOUR_ALERTS_TITLE, strings.FEATURE_TOUR_ALERTS_DESC)
        add_feature("fa5s.print", strings.FEATURE_TOUR_PRINT_TITLE, strings.FEATURE_TOUR_PRINT_DESC)
        
        features_layout.addStretch(1)
        scroll.setWidget(container)
        layout.addWidget(scroll, stretch=1)

        close_btn = QPushButton(strings.ACTION_CLOSE)
        close_btn.setObjectName("Primary")
        close_btn.clicked.connect(self.accept)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch(1)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)
