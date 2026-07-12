"""Tableau de bord — the at-a-glance home screen.

Aggregates figures already exposed by the statistics / alerts endpoints into
four KPI cards (each with a colour-coded left border), a 7-day revenue trend,
the month's top 5 products, a financial snapshot and the last 5 sales. Every
call goes through run_api; the whole board auto-refreshes every 60 s and can
be refreshed by hand from the header.
"""

from datetime import date
from decimal import Decimal

import qtawesome as qta
import shiboken6
from PySide6.QtCore import QDate, Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from services.workers import run_api
from ui import format as fmt
from ui import strings
from ui.screens.statistics import RankBars
from ui.styles.tokens import ICON_SIZES, NEUTRAL, RADIUS, SPACING
from ui.widgets.card import SectionCard
from ui.widgets.charts import LineChart, LinePoint

# KPI palette: (foreground, subtle tint) — decorative, kept out of the
# themeable accent tokens so the board stays colourful under any accent.
_KPI_GREEN = ("#16A34A", "#DCFCE7")
_KPI_BLUE = ("#2563EB", "#DBEAFE")
_KPI_RED = ("#DC2626", "#FEE2E2")
_KPI_ORANGE = ("#D97706", "#FEF3C7")

_TOP_BAR_COLOR = "#2563EB"


class KpiBorderCard(QFrame):
    """Metric card with a colour-coded left border + an icon chip.

    Clickable when `on_click` is given (used by the low-stock card to jump to
    the Alertes screen). The left strip lives at the leading edge of a
    horizontal layout, so it mirrors correctly to the right under RTL.
    """

    def __init__(self, caption, icon, color, bg, on_click=None, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._on_click = on_click
        if on_click is not None:
            self.setCursor(Qt.CursorShape.PointingHandCursor)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        strip = QFrame()
        strip.setFixedWidth(4)
        strip.setStyleSheet(
            f"background: {color}; "
            f"border-top-left-radius: {RADIUS['md']}px; "
            f"border-bottom-left-radius: {RADIUS['md']}px;"
        )
        outer.addWidget(strip)

        inner = QVBoxLayout()
        inner.setContentsMargins(
            SPACING["lg"], SPACING["lg"], SPACING["lg"], SPACING["lg"]
        )
        inner.setSpacing(SPACING["sm"])
        top = QHBoxLayout()
        top.setSpacing(SPACING["sm"])
        chip = QLabel()
        chip.setFixedSize(40, 40)
        chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        chip.setPixmap(
            qta.icon(icon, color=color).pixmap(ICON_SIZES["lg"], ICON_SIZES["lg"])
        )
        chip.setStyleSheet(f"background: {bg}; border-radius: {RADIUS['md']}px;")
        top.addWidget(chip)
        caption_label = QLabel(caption)
        caption_label.setObjectName("StatCardTitle")
        caption_label.setWordWrap(True)
        top.addWidget(caption_label, 1)
        inner.addLayout(top)

        self._value = QLabel("—")
        self._value.setObjectName("StatCardValue")
        self._value.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        inner.addWidget(self._value)
        outer.addLayout(inner, 1)

    def set_value(self, text: str) -> None:
        self._value.setText(text)

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if self._on_click is not None and event.button() == Qt.MouseButton.LeftButton:
            self._on_click()
        super().mousePressEvent(event)


class DashboardScreen(QWidget):
    def __init__(self, api, store_id: str, on_open_alerts=None, parent=None) -> None:
        super().__init__(parent)
        self.api = api
        self.store_id = store_id
        self._on_open_alerts = on_open_alerts

        outer = QVBoxLayout(self)
        outer.setContentsMargins(*[SPACING["xl"]] * 4)
        outer.setSpacing(SPACING["md"])
        outer.addLayout(self._build_header())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, SPACING["sm"], 0)
        layout.setSpacing(SPACING["lg"])
        layout.addLayout(self._build_kpi_row())
        layout.addLayout(self._build_middle_row())
        layout.addLayout(self._build_bottom_row())
        layout.addStretch(1)
        scroll.setWidget(content)
        outer.addWidget(scroll, stretch=1)

        # Auto-refresh every 60 s while the app is open.
        self._timer = QTimer(self)
        self._timer.setInterval(60_000)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()

    # --------------------------------------------------------------- build

    def _build_header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        title = QLabel(strings.DASHBOARD_TITLE)
        title.setObjectName("ScreenTitle")
        row.addWidget(title)
        row.addStretch(1)
        refresh = QPushButton(
            qta.icon("fa5s.sync", color=NEUTRAL["600"]), strings.REFRESH
        )
        refresh.setObjectName("Primary")
        refresh.clicked.connect(self.refresh)
        row.addWidget(refresh)
        return row

    def _build_kpi_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(SPACING["md"])
        self.kpi_revenue = KpiBorderCard(
            strings.DASH_TODAY_REVENUE, "fa5s.coins", *_KPI_GREEN
        )
        self.kpi_sales = KpiBorderCard(
            strings.DASH_TODAY_SALES, "fa5s.receipt", *_KPI_BLUE
        )
        self.kpi_low_stock = KpiBorderCard(
            strings.DASH_LOW_STOCK,
            "fa5s.exclamation-triangle",
            *_KPI_RED,
            on_click=self._open_alerts,
        )
        self.kpi_credit = KpiBorderCard(
            strings.DASH_OUTSTANDING, "fa5s.hand-holding-usd", *_KPI_ORANGE
        )
        for card in (
            self.kpi_revenue,
            self.kpi_sales,
            self.kpi_low_stock,
            self.kpi_credit,
        ):
            row.addWidget(card, stretch=1)
        return row

    def _build_middle_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(SPACING["md"])

        trend_card = SectionCard(strings.DASH_TREND_TITLE, "fa5s.chart-line")
        self.trend_chart = LineChart()
        self.trend_chart.setMinimumHeight(220)
        trend_card.body.addWidget(self.trend_chart)
        row.addWidget(trend_card, stretch=3)

        top_card = SectionCard(strings.DASH_TOP_PRODUCTS, "fa5s.crown")
        self.top_bars = RankBars()
        top_card.body.addWidget(self.top_bars)
        top_card.body.addStretch(1)
        row.addWidget(top_card, stretch=2)
        return row

    def _build_bottom_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(SPACING["md"])

        fin_card = SectionCard(strings.DASH_FINANCIAL, "fa5s.balance-scale")
        self.fin_credit = self._fin_row(fin_card, strings.DASH_CUSTOMER_CREDIT)
        self.fin_debt = self._fin_row(fin_card, strings.DASH_SUPPLIER_DEBT)
        fin_card.body.addStretch(1)
        row.addWidget(fin_card, stretch=1)

        activity_card = SectionCard(strings.DASH_RECENT_ACTIVITY, "fa5s.history")
        self.activity_holder = QWidget()
        self.activity_layout = QVBoxLayout(self.activity_holder)
        self.activity_layout.setContentsMargins(0, 0, 0, 0)
        self.activity_layout.setSpacing(SPACING["xs"])
        activity_card.body.addWidget(self.activity_holder)
        activity_card.body.addStretch(1)
        row.addWidget(activity_card, stretch=1)
        return row

    def _fin_row(self, card: SectionCard, caption: str) -> QLabel:
        row = QHBoxLayout()
        caption_label = QLabel(caption)
        caption_label.setObjectName("Secondary")
        row.addWidget(caption_label)
        row.addStretch(1)
        value = QLabel("—")
        value.setStyleSheet("font-weight: 700; background: transparent;")
        row.addWidget(value)
        card.body.addLayout(row)
        return value

    # ------------------------------------------------------------- loading

    def refresh(self) -> None:
        if not shiboken6.isValid(self):
            return
        today = date.today()
        today_iso = today.isoformat()
        week_from = (QDate.currentDate().addDays(-6)).toString("yyyy-MM-dd")
        month_from = QDate(today.year, today.month, 1).toString("yyyy-MM-dd")

        run_api(
            lambda: self.api.stats_overview(self.store_id),
            self._on_overview,
            lambda err: None,
        )
        run_api(
            lambda: self.api.get_alerts(self.store_id),
            self._on_alerts,
            lambda err: None,
        )
        run_api(
            lambda: self.api.stats_financial_snapshot(self.store_id),
            self._on_financial,
            lambda err: None,
        )
        run_api(
            lambda: self.api.stats_daily_evolution(self.store_id, week_from, today_iso),
            self._on_trend,
            lambda err: None,
        )
        run_api(
            lambda: self.api.stats_top_products(
                self.store_id, month_from, today_iso, limit=5
            ),
            self._on_top,
            lambda err: None,
        )
        run_api(
            lambda: self.api.list_sales(self.store_id, limit=5),
            self._on_recent,
            lambda err: None,
        )

    # ------------------------------------------------------------ handlers

    def _on_overview(self, overview: object) -> None:
        if not shiboken6.isValid(self):
            return
        today = next(
            (p for p in overview.get("periods", []) if p.get("period") == "today"),
            None,
        )
        if today is None:
            return
        current = today.get("current", {})
        self.kpi_revenue.set_value(fmt.fmt_money(current.get("revenue", 0)))
        self.kpi_sales.set_value(str(int(current.get("sales_count", 0))))

    def _on_alerts(self, alerts: object) -> None:
        if not shiboken6.isValid(self):
            return
        summary = alerts.get("summary", {})
        self.kpi_low_stock.set_value(str(int(summary.get("low_stock_count", 0))))

    def _on_financial(self, fin: object) -> None:
        if not shiboken6.isValid(self):
            return
        self.kpi_credit.set_value(fmt.fmt_money(fin.get("customer_credit_total", 0)))
        self.fin_credit.setText(fmt.fmt_money(fin.get("customer_credit_total", 0)))
        self.fin_debt.setText(fmt.fmt_money(fin.get("supplier_debt_total", 0)))

    def _on_trend(self, points: object) -> None:
        if not shiboken6.isValid(self):
            return
        series = [
            LinePoint(
                day=date.fromisoformat(p["day"]),
                revenue=Decimal(str(p["revenue"])),
                profit=Decimal(str(p["profit"])),
            )
            for p in points
        ]
        self.trend_chart.set_data(series)

    def _on_top(self, top: object) -> None:
        if not shiboken6.isValid(self):
            return
        top = list(top)
        if not top:
            self.top_bars.set_rows([])
            return
        max_qty = max((int(t.get("quantity_sold", 0)) for t in top), default=0) or 1
        rows = []
        for t in top:
            qty = int(t.get("quantity_sold", 0))
            name = t["name"][:16] + "…" if len(t["name"]) > 16 else t["name"]
            rows.append((name, str(qty), qty / max_qty, _TOP_BAR_COLOR))
        self.top_bars.set_rows(rows)

    def _on_recent(self, sales: object) -> None:
        if not shiboken6.isValid(self):
            return
        while self.activity_layout.count():
            item = self.activity_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        sales = list(sales)[:5]
        if not sales:
            empty = QLabel(strings.DASH_NO_ACTIVITY)
            empty.setObjectName("Muted")
            self.activity_layout.addWidget(empty)
            return
        for sale in sales:
            self.activity_layout.addWidget(self._activity_row(sale))

    def _activity_row(self, sale: dict) -> QWidget:
        row_widget = QFrame()
        row_widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        row = QHBoxLayout(row_widget)
        row.setContentsMargins(0, 2, 0, 2)
        row.setSpacing(SPACING["sm"])
        time_label = QLabel(fmt.fmt_short_datetime(sale.get("created_at")))
        time_label.setObjectName("Muted")
        row.addWidget(time_label)
        who = sale.get("customer_name") or strings.DASH_ANONYMOUS
        who_label = QLabel(who)
        who_label.setStyleSheet("background: transparent;")
        row.addWidget(who_label, 1)
        amount = QLabel(fmt.fmt_money(sale.get("total_amount", 0)))
        amount.setStyleSheet("font-weight: 700; background: transparent;")
        row.addWidget(amount)
        return row_widget

    # ------------------------------------------------------------- actions

    def _open_alerts(self) -> None:
        if self._on_open_alerts is not None:
            self._on_open_alerts()
