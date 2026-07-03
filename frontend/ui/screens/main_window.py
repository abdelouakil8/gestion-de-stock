"""Application shell — frameless window, custom title bar, sidebar navigation.

Direction-agnostic layouts throughout: with Qt.RightToLeft (Arabic update,
or the POS_FORCE_RTL dev toggle) every screen mirrors correctly — the nav
active indicator, icons and badges all live in layouts, never absolute
positions.

The Alertes nav item carries a live badge (low stock + outstanding credits)
refreshed by a 30 s poll and after every checkout / payment — both through
worker threads, never on the UI thread.
"""

import qtawesome as qta
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizeGrip,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from services import image_cache
from services.workers import run_api
from ui import strings
from ui.screens.alerts import AlertsScreen
from ui.screens.checkout import CheckoutScreen
from ui.screens.customers import CustomersScreen
from ui.screens.inventory import InventoryScreen
from ui.screens.settings_screen import SettingsScreen
from ui.screens.statistics import StatisticsScreen
from ui.styles.tokens import ICON_SIZES, NEUTRAL, SPACING


class TitleBar(QWidget):
    """Draggable custom title bar with working min/max/close."""

    def __init__(self, window: QMainWindow) -> None:
        super().__init__(window)
        self.setObjectName("TitleBar")
        self._window = window

        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACING["md"], 0, 0, 0)
        layout.setSpacing(SPACING["sm"])

        brand_icon = QLabel()
        brand_icon.setPixmap(
            qta.icon("fa5s.store", color=NEUTRAL["400"]).pixmap(
                ICON_SIZES["sm"], ICON_SIZES["sm"]
            )
        )
        brand_icon.setStyleSheet("background: transparent;")
        layout.addWidget(brand_icon)
        layout.addWidget(QLabel(strings.APP_TITLE))
        layout.addStretch(1)

        minimize = QPushButton("–")
        minimize.clicked.connect(window.showMinimized)
        self.maximize = QPushButton("□")
        self.maximize.clicked.connect(self._toggle_maximize)
        close = QPushButton("✕")
        close.setObjectName("TitleBarClose")
        close.clicked.connect(window.close)
        for button in (minimize, self.maximize, close):
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            layout.addWidget(button)

    def _toggle_maximize(self) -> None:
        if self._window.isMaximized():
            self._window.showNormal()
        else:
            self._window.showMaximized()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._window.windowHandle().startSystemMove()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        self._toggle_maximize()
        super().mouseDoubleClickEvent(event)


class NavButton(QPushButton):
    """Sidebar item: indicator strip + icon + label + optional badge.

    Everything sits in a layout, so RTL mirrors the whole row (indicator
    included) without a single absolute coordinate.
    """

    def __init__(self, icon_name: str, label: str) -> None:
        super().__init__()
        self.setObjectName("NavButton")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACING["sm"], 0, SPACING["md"], 0)
        layout.setSpacing(SPACING["md"])

        self._indicator = QFrame()
        self._indicator.setObjectName("NavIndicator")
        self._indicator.setFixedSize(4, 22)
        layout.addWidget(self._indicator)

        self._icon = QLabel()
        self._icon_name = icon_name
        self._icon.setStyleSheet("background: transparent;")
        layout.addWidget(self._icon)

        self._label = QLabel(label)
        self._label.setObjectName("NavLabel")
        layout.addWidget(self._label)
        layout.addStretch(1)

        self._badge = QLabel("")
        self._badge.setObjectName("NavBadge")
        self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._badge.hide()
        layout.addWidget(self._badge)

        self.toggled.connect(self._refresh_state)
        self._refresh_state(False)

    def _refresh_state(self, checked: bool) -> None:
        color = "#FFFFFF" if checked else NEUTRAL["400"]
        self._icon.setPixmap(
            qta.icon(self._icon_name, color=color).pixmap(
                ICON_SIZES["md"], ICON_SIZES["md"]
            )
        )
        self._indicator.setProperty("active", "true" if checked else "false")
        self._indicator.style().unpolish(self._indicator)
        self._indicator.style().polish(self._indicator)

    def set_badge(self, count: int) -> None:
        if count > 0:
            self._badge.setText("99+" if count > 99 else str(count))
            self._badge.show()
        else:
            self._badge.hide()


class MainWindow(QMainWindow):
    def __init__(self, api, store: dict) -> None:
        super().__init__()
        self.api = api
        self.store = store
        image_cache.init(api)

        self.setWindowTitle(strings.APP_TITLE)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.resize(1180, 720)
        self.setMinimumSize(960, 580)

        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(TitleBar(self))

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        nav = QVBoxLayout(sidebar)
        nav.setContentsMargins(
            SPACING["sm"], SPACING["lg"], SPACING["sm"], SPACING["lg"]
        )
        nav.setSpacing(4)

        section = QLabel(strings.NAV_SECTION)
        section.setObjectName("SidebarHeader")
        section.setContentsMargins(SPACING["sm"], 0, SPACING["sm"], SPACING["xs"])
        nav.addWidget(section)

        self.stack = QStackedWidget()
        self.checkout = CheckoutScreen(api, store["id"])
        self.inventory = InventoryScreen(api, store["id"])
        self.customers = CustomersScreen(api, store["id"])
        self.statistics = StatisticsScreen(api, store["id"])
        self.alerts = AlertsScreen(api, store["id"], self._open_product_from_alert)
        self.settings_screen = SettingsScreen(api, store)

        self._nav_buttons: list[NavButton] = []
        for icon_name, label, screen in [
            ("fa5s.cash-register", strings.NAV_CHECKOUT, self.checkout),
            ("fa5s.boxes", strings.NAV_INVENTORY, self.inventory),
            ("fa5s.users", strings.NAV_CUSTOMERS, self.customers),
            ("fa5s.chart-line", strings.NAV_STATISTICS, self.statistics),
            ("fa5s.bell", strings.NAV_ALERTS, self.alerts),
            ("fa5s.cog", strings.NAV_SETTINGS, self.settings_screen),
        ]:
            self.stack.addWidget(screen)
            button = NavButton(icon_name, label)
            button.clicked.connect(lambda _, s=screen: self.navigate(s))
            nav.addWidget(button)
            self._nav_buttons.append(button)
        nav.addStretch(1)
        self.alerts_nav = self._nav_buttons[4]

        body.addWidget(sidebar)
        body.addWidget(self.stack, stretch=1)
        root_layout.addLayout(body, stretch=1)

        grip_row = QHBoxLayout()
        grip_row.setContentsMargins(0, 0, 0, 0)
        grip_row.addStretch(1)
        grip_row.addWidget(QSizeGrip(root))
        root_layout.addLayout(grip_row)

        self.setCentralWidget(root)
        self.navigate(self.checkout)

        # Alerts badge: poll every 30 s + explicit refreshes after actions.
        self._alerts_timer = QTimer(self)
        self._alerts_timer.setInterval(30_000)
        self._alerts_timer.timeout.connect(self.refresh_alerts_badge)
        self._alerts_timer.start()
        self.refresh_alerts_badge()

    # ---------------------------------------------------------- navigation

    def navigate(self, screen: QWidget) -> None:
        self.stack.setCurrentWidget(screen)
        for index, button in enumerate(self._nav_buttons):
            button.setChecked(self.stack.widget(index + 0) is screen)
        if screen is self.checkout:
            self.checkout.search.setFocus()
        elif hasattr(screen, "refresh"):
            screen.refresh()

    def _open_product_from_alert(self, product_id: str) -> None:
        self.navigate(self.inventory)
        self.inventory.focus_product(product_id)

    # -------------------------------------------------------------- alerts

    def refresh_alerts_badge(self) -> None:
        run_api(
            lambda: self.api.get_alerts(self.store["id"]),
            self._on_alerts,
            lambda err: None,  # badge is best-effort; screens report errors
        )

    def _on_alerts(self, alerts: object) -> None:
        summary = alerts.get("summary", {})
        count = summary.get("low_stock_count", 0) + summary.get(
            "outstanding_credits_count", 0
        )
        self.alerts_nav.set_badge(count)
        self.alerts.set_data(alerts)

    def resizeEvent(self, event) -> None:
        toast = getattr(self, "_active_toast", None)
        if toast is not None:
            toast.reposition()
        super().resizeEvent(event)
