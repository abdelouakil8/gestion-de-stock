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
from ui.screens.creances import CreancesScreen
from ui.screens.customers import CustomersScreen
from ui.screens.dashboard import DashboardScreen
from ui.screens.inventory import InventoryScreen
from ui.screens.settings_screen import SettingsScreen
from ui.screens.statistics import StatisticsScreen
from ui.screens.suppliers import SuppliersScreen
from ui.screens.ventes import VentesScreen
from ui.styles.tokens import ICON_SIZES, NEUTRAL, SPACING

# Role privilege order — the sidebar shows an item when the user's rank is at
# or above the item's minimum.
_ROLE_RANK = {"cashier": 0, "manager": 1, "owner": 2}


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
        brand = QLabel(strings.APP_TITLE)
        # Quiet chrome: the brand mark uses the muted caption style so the
        # visual weight stays on the screen content, not the window frame.
        brand.setObjectName("TitleBarBrand")
        layout.addWidget(brand)
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

        # LAZY screens: nothing heavy is built here. Each screen is created
        # the FIRST time the operator opens it, so the window appears right
        # after the PIN instead of paying for all twelve screens up front.
        self.stack = QStackedWidget()
        self._screens: dict[str, QWidget] = {}
        self._factories = {
            "dashboard": lambda: DashboardScreen(
                api,
                store["id"],
                on_open_alerts=lambda: self.navigate("alerts"),
            ),
            "checkout": lambda: CheckoutScreen(api, store["id"]),
            "inventory": lambda: InventoryScreen(api, store["id"]),
            "customers": lambda: CustomersScreen(api, store["id"]),
            "ventes": lambda: VentesScreen(
                api, store["id"], on_view_product=self._open_product_from_alert
            ),
            "creances": lambda: CreancesScreen(api, store["id"]),
            "statistics": lambda: StatisticsScreen(api, store["id"]),
            "suppliers": lambda: SuppliersScreen(api, store["id"]),
            "alerts": lambda: AlertsScreen(
                api,
                store["id"],
                self._open_product_from_alert,
                self._open_purchase_from_alert,
            ),
            "settings": lambda: SettingsScreen(api, store),
        }

        # Role-gated navigation. Each item declares the minimum role that may
        # see it; visibility is monotonic (cashier ⊂ manager ⊂ owner):
        #   cashier → Caisse + Ventes (own); manager → everything but
        #   Statistiques & Réglages; owner → everything. Legacy/open mode
        #   (no session) is treated as owner so nothing is hidden.
        role = self.api.role or "owner"
        rank = _ROLE_RANK.get(role, _ROLE_RANK["owner"])

        self._nav_by_key: dict[str, NavButton] = {}
        for icon_name, label, key, min_role in [
            ("fa5s.tachometer-alt", strings.NAV_DASHBOARD, "dashboard", "manager"),
            ("fa5s.cash-register", strings.NAV_CHECKOUT, "checkout", "cashier"),
            ("fa5s.boxes", strings.NAV_INVENTORY, "inventory", "manager"),
            ("fa5s.users", strings.NAV_CUSTOMERS, "customers", "manager"),
            ("fa5s.receipt", strings.NAV_SALES, "ventes", "cashier"),
            ("fa5s.hand-holding-usd", strings.NAV_CREANCES, "creances", "manager"),
            ("fa5s.truck", strings.NAV_PURCHASES, "suppliers", "manager"),
            ("fa5s.chart-line", strings.NAV_STATISTICS, "statistics", "owner"),
            ("fa5s.bell", strings.NAV_ALERTS, "alerts", "manager"),
            ("fa5s.cog", strings.NAV_SETTINGS, "settings", "owner"),
        ]:
            button = NavButton(icon_name, label)
            button.clicked.connect(lambda _, k=key: self.navigate(k))
            button.setVisible(rank >= _ROLE_RANK[min_role])
            nav.addWidget(button)
            self._nav_by_key[key] = button
        # The Alertes item carries the live badge updated by the poll.
        self.alerts_nav = self._nav_by_key["alerts"]
        nav.addStretch(1)

        body.addWidget(sidebar)
        body.addWidget(self.stack, stretch=1)
        root_layout.addLayout(body, stretch=1)

        # Landing screen: the dashboard for manager/owner, the caisse for a
        # cashier (who cannot see the dashboard).
        self._default_screen = (
            "dashboard" if rank >= _ROLE_RANK["manager"] else "checkout"
        )

        # Resize grip OVERLAYED in the end corner — a dedicated layout row
        # would paint a full-width strip under the sidebar (white band bug).
        self._size_grip = QSizeGrip(root)
        self._size_grip.setFixedSize(16, 16)
        self._size_grip.setStyleSheet("background: transparent;")
        self._size_grip.raise_()

        self.setCentralWidget(root)
        self.navigate(self._default_screen)

        # Alerts badge: poll every 30 s + explicit refreshes after actions.
        self._alerts_timer = QTimer(self)
        self._alerts_timer.setInterval(30_000)
        self._alerts_timer.timeout.connect(self.refresh_alerts_badge)
        self._alerts_timer.start()
        self.refresh_alerts_badge()
        self._check_for_updates()

    def _check_for_updates(self) -> None:
        from services.updater import check_for_update

        run_api(
            check_for_update,
            self._on_update_checked,
            lambda err: None,
        )

    def _on_update_checked(self, info: object) -> None:
        if info:
            from ui.widgets.toast import show_toast

            msg = (
                f"{strings.UPDATE_AVAILABLE.format(version=info.version)}\n"
                f"{strings.UPDATE_AVAILABLE_HINT.format(url=info.download_url)}"
            )
            show_toast(self, msg, duration=10000)

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

    # ------------------------------------------------------- lazy screens

    def screen(self, key: str) -> QWidget:
        """The screen for `key`, built on first access (lazy)."""
        widget = self._screens.get(key)
        if widget is None:
            widget = self._factories[key]()
            self._screens[key] = widget
            self.stack.addWidget(widget)
        return widget

    # Attribute-style accessors kept for existing callers (feature tour,
    # settings language switch…). Reading one builds the screen on demand.
    @property
    def dashboard(self) -> QWidget:
        return self.screen("dashboard")

    @property
    def checkout(self) -> QWidget:
        return self.screen("checkout")

    @property
    def inventory(self) -> QWidget:
        return self.screen("inventory")

    @property
    def customers(self) -> QWidget:
        return self.screen("customers")

    @property
    def ventes(self) -> QWidget:
        return self.screen("ventes")

    @property
    def creances(self) -> QWidget:
        return self.screen("creances")

    @property
    def statistics(self) -> QWidget:
        return self.screen("statistics")

    @property
    def suppliers_screen(self) -> QWidget:
        return self.screen("suppliers")

    @property
    def alerts(self) -> QWidget:
        return self.screen("alerts")

    @property
    def settings_screen(self) -> QWidget:
        return self.screen("settings")

    # ---------------------------------------------------------- navigation

    def navigate(self, target) -> None:
        """Show a screen — accepts the screen key or the widget itself."""
        if isinstance(target, str):
            key = target
        else:
            key = next((k for k, w in self._screens.items() if w is target), None)
            if key is None:
                return
        screen = self.screen(key)
        self.stack.setCurrentWidget(screen)
        for k, button in self._nav_by_key.items():
            button.setChecked(k == key)
        if key == "checkout":
            screen.search.setFocus()
        elif hasattr(screen, "refresh"):
            screen.refresh()

    def _open_product_from_alert(self, product_id: str) -> None:
        self.navigate("inventory")
        self.inventory.focus_product(product_id)

    def _open_purchase_from_alert(self, product: dict) -> None:
        """From a dead-stock row: open Achats & Fournisseurs and start a new
        purchase order with this product pre-filled as the first line."""
        self.navigate("suppliers")
        self.suppliers_screen.open_new_purchase_order(prefill_product=product)

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
        # Feed the Alertes screen only if it exists — building it here would
        # defeat the lazy startup (it refreshes itself on first navigation).
        alerts_screen = self._screens.get("alerts")
        if alerts_screen is not None:
            alerts_screen.set_data(alerts)

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
