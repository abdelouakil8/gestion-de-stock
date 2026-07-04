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
from PySide6.QtGui import QKeySequence, QShortcut
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
from ui.screens.ventes import VentesScreen
from ui.styles.tokens import ICON_SIZES, NEUTRAL, SPACING


class TitleBar(QWidget):
    """Draggable custom title bar — always-visible icon buttons for
    minimize / fullscreen / maximize / close (no hover needed to see
    them), plus F11-driven fullscreen handled by the window."""

    def __init__(self, window: QMainWindow) -> None:
        super().__init__(window)
        self.setObjectName("TitleBar")
        # Custom QWidget subclasses ignore QSS backgrounds without this —
        # the bar would paint WHITE and drown the light icons.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
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

        def window_button(icon_name: str, tooltip: str) -> QPushButton:
            button = QPushButton()
            # Pure white in every icon mode — clearly visible at all times.
            button.setIcon(qta.icon(icon_name, color="white", color_active="white"))
            button.setToolTip(tooltip)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            layout.addWidget(button)
            return button

        minimize = window_button("fa5s.window-minimize", strings.TITLEBAR_MINIMIZE)
        minimize.clicked.connect(window.showMinimized)
        self.fullscreen = window_button("fa5s.expand", strings.TITLEBAR_FULLSCREEN)
        self.fullscreen.clicked.connect(self.toggle_fullscreen)
        self.maximize = window_button("fa5s.window-maximize", strings.TITLEBAR_MAXIMIZE)
        self.maximize.clicked.connect(self._toggle_maximize)
        close = window_button("fa5s.times", strings.TITLEBAR_CLOSE)
        close.setObjectName("TitleBarClose")
        close.clicked.connect(window.close)

    def _refresh_state_icons(self) -> None:
        maximized = self._window.isMaximized()
        fullscreen = self._window.isFullScreen()
        self.maximize.setIcon(
            qta.icon(
                "fa5s.window-restore" if maximized else "fa5s.window-maximize",
                color="white",
                color_active="white",
            )
        )
        self.maximize.setToolTip(
            strings.TITLEBAR_RESTORE if maximized else strings.TITLEBAR_MAXIMIZE
        )
        self.fullscreen.setIcon(
            qta.icon(
                "fa5s.compress" if fullscreen else "fa5s.expand",
                color="white",
                color_active="white",
            )
        )
        self.fullscreen.setToolTip(
            strings.TITLEBAR_EXIT_FULLSCREEN
            if fullscreen
            else strings.TITLEBAR_FULLSCREEN
        )

    def _toggle_maximize(self) -> None:
        if self._window.isFullScreen():
            self._window.showNormal()
        elif self._window.isMaximized():
            self._window.showNormal()
        else:
            self._window.showMaximized()
        self._refresh_state_icons()

    def toggle_fullscreen(self) -> None:
        """Fill the entire screen (F11 or the expand button)."""
        if self._window.isFullScreen():
            self._window.showNormal()
        else:
            self._window.showFullScreen()
        self._refresh_state_icons()

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
        self._fit_to_screen()

        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self.title_bar = TitleBar(self)
        root_layout.addWidget(self.title_bar)
        QShortcut(
            QKeySequence(Qt.Key.Key_F11),
            self,
            activated=self.title_bar.toggle_fullscreen,
        )

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
        self.ventes = VentesScreen(
            api, store["id"], on_view_product=self._open_product_from_alert
        )
        self.statistics = StatisticsScreen(api, store["id"])
        self.alerts = AlertsScreen(api, store["id"], self._open_product_from_alert)
        self.settings_screen = SettingsScreen(api, store)

        self._nav_buttons: list[NavButton] = []
        for icon_name, label, screen in [
            ("fa5s.cash-register", strings.NAV_CHECKOUT, self.checkout),
            ("fa5s.boxes", strings.NAV_INVENTORY, self.inventory),
            ("fa5s.users", strings.NAV_CUSTOMERS, self.customers),
            ("fa5s.receipt", strings.NAV_SALES, self.ventes),
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
        self.alerts_nav = self._nav_buttons[5]

        body.addWidget(sidebar)
        body.addWidget(self.stack, stretch=1)
        root_layout.addLayout(body, stretch=1)

        # Resize grip OVERLAYED in the end corner — a dedicated layout row
        # would paint a full-width strip under the sidebar (white band bug).
        self._size_grip = QSizeGrip(root)
        self._size_grip.setFixedSize(16, 16)
        self._size_grip.setStyleSheet("background: transparent;")
        self._size_grip.raise_()

        self.setCentralWidget(root)
        self.navigate(self.checkout)

        # Alerts badge: poll every 30 s + explicit refreshes after actions.
        self._alerts_timer = QTimer(self)
        self._alerts_timer.setInterval(30_000)
        self._alerts_timer.timeout.connect(self.refresh_alerts_badge)
        self._alerts_timer.start()
        self.refresh_alerts_badge()

    def _fit_to_screen(self) -> None:
        """Size and center the window for ANY display: preferred 1180×720,
        clamped to the actual available screen (taskbar excluded) so the
        app never opens larger than the monitor."""
        from PySide6.QtWidgets import QApplication

        screen = QApplication.primaryScreen()
        if screen is None:
            self.resize(1180, 720)
            return
        available = screen.availableGeometry()
        width = min(1180, available.width() - 16)
        height = min(720, available.height() - 16)
        self.setMinimumSize(
            min(920, available.width() - 16), min(560, available.height() - 16)
        )
        self.resize(width, height)
        frame = self.frameGeometry()
        frame.moveCenter(available.center())
        self.move(frame.topLeft())

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
        # Keep the overlayed size grip pinned to the END corner (mirrors
        # under RTL — computed from layoutDirection, no absolute side).
        grip = getattr(self, "_size_grip", None)
        if grip is not None and self.centralWidget() is not None:
            area = self.centralWidget().rect()
            if self.layoutDirection() == Qt.LayoutDirection.RightToLeft:
                grip.move(area.left(), area.bottom() - grip.height() + 1)
            else:
                grip.move(
                    area.right() - grip.width() + 1,
                    area.bottom() - grip.height() + 1,
                )
        super().resizeEvent(event)
