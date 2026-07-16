"""Statistics dashboard screen — the main StatisticsScreen widget."""

import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import qtawesome as qta
from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QDateEdit,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from services.workers import run_api
from ui import format as fmt
from ui import strings
from ui.styles.tokens import NEUTRAL, SPACING, THUMB_SIZES
from ui.widgets.card import SectionCard
from ui.widgets.charts import ColumnChart, DonutChart, LineChart, LinePoint
from ui.widgets.data_table import DataTable
from ui.widgets.modal import show_error
from ui.widgets.period_comparison import PeriodComparisonTab
from ui.widgets.states import EmptyState, StatefulStack
from ui.widgets.thumb import Thumb

from ._cards import (
    _CAT_PALETTE,
    _KPI_AMBER,
    _KPI_BLUE,
    _KPI_GREEN,
    _KPI_RED,
    _KPI_VIOLET,
    KpiCard,
    RankBars,
    RuleCard,
    _DailyReportDatePicker,
)


class StatisticsScreen(QWidget):
    def __init__(self, api, store_id: str, parent=None) -> None:
        super().__init__(parent)
        self.api = api
        self.store_id = store_id
        self.products_by_id: dict[str, dict] = {}

        # Section state driven by the in-card toggles.
        self._top_sort = "quantity"
        self._dead_days = 60
        self._busy_mode = "hours"
        self._patterns: dict | None = None
        self._categories: list | None = None
        self._cur_summary: dict | None = None
        self._prev_summary: dict | None = None
        self._insights: dict | None = None
        self._top_data: list = []

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
        layout.addWidget(self._build_trend())
        layout.addLayout(self._build_snapshot_row())
        layout.addLayout(self._build_products_row())
        layout.addLayout(self._build_patterns_row())
        layout.addLayout(self._build_lower_row())
        layout.addWidget(self._build_associations())
        layout.addStretch(1)

        scroll.setWidget(content)

        # Tabbed: the live dashboard + a period-comparison tab (lazy-loaded).
        self.tabs = QTabWidget()
        self.tabs.addTab(scroll, strings.STATS_TAB_DASHBOARD)
        self.comparison_tab = PeriodComparisonTab(self.api, self.store_id)
        self._comparison_loaded = False
        self.tabs.addTab(self.comparison_tab, strings.STATS_TAB_COMPARISON)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        outer.addWidget(self.tabs, stretch=1)

    def _on_tab_changed(self, index: int) -> None:
        if (
            self.tabs.widget(index) is self.comparison_tab
            and not self._comparison_loaded
        ):
            self._comparison_loaded = True
            self.comparison_tab.refresh()

    # --------------------------------------------------------------- build

    def _build_header(self) -> QVBoxLayout:
        box = QVBoxLayout()
        box.setSpacing(SPACING["md"])

        row1 = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(0)
        title = QLabel(strings.STATISTICS_TITLE)
        title.setObjectName("ScreenTitle")
        title_box.addWidget(title)
        subtitle = QLabel(strings.STATS_SUBTITLE)
        subtitle.setObjectName("Muted")
        title_box.addWidget(subtitle)
        row1.addLayout(title_box)
        row1.addStretch(1)

        self.btn_daily_report = QPushButton(
            qta.icon("fa5s.calendar-day", color=NEUTRAL["600"]),
            strings.STATS_DAILY_REPORT,
        )
        self.btn_daily_report.setObjectName("Secondary")
        self.btn_daily_report.clicked.connect(self._daily_report)
        row1.addWidget(self.btn_daily_report)

        self.btn_export_pdf = QPushButton(strings.STATS_EXPORT_PDF)
        self.btn_export_pdf.setObjectName("Secondary")
        self.btn_export_pdf.clicked.connect(self.export_pdf)
        row1.addWidget(self.btn_export_pdf)

        self.btn_export_xlsx = QPushButton(strings.STATS_EXPORT_XLSX)
        self.btn_export_xlsx.setObjectName("Secondary")
        self.btn_export_xlsx.clicked.connect(self.export_xlsx)
        row1.addWidget(self.btn_export_xlsx)

        refresh = QPushButton(strings.REFRESH)
        refresh.setObjectName("Primary")
        refresh.clicked.connect(self.refresh)
        row1.addWidget(refresh)
        box.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(self._build_presets())
        row2.addStretch(1)
        row2.addWidget(self._build_date_range())
        box.addLayout(row2)

        self._preset_buttons["30d"].setChecked(True)
        return box

    def _build_presets(self) -> QWidget:
        group = QWidget()
        group.setObjectName("SegmentGroup")
        group.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QHBoxLayout(group)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(3)
        self._preset_group = QButtonGroup(self)
        self._preset_group.setExclusive(True)
        self._preset_buttons: dict[str, QPushButton] = {}
        presets = [
            ("today", strings.STATS_PRESET_TODAY),
            ("7d", strings.STATS_PRESET_7D),
            ("30d", strings.STATS_PRESET_30D),
            ("month", strings.STATS_THIS_MONTH),
            ("year", strings.STATS_THIS_YEAR),
        ]
        for key, label in presets:
            button = QPushButton(label)
            button.setObjectName("SegmentPill")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _=False, k=key: self._apply_preset(k))
            self._preset_group.addButton(button)
            layout.addWidget(button)
            self._preset_buttons[key] = button
        return group

    def _build_date_range(self) -> QWidget:
        box = QWidget()
        box.setObjectName("DateRangeBox")
        box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QHBoxLayout(box)
        layout.setContentsMargins(SPACING["sm"], 2, SPACING["sm"], 2)
        layout.setSpacing(SPACING["xs"])

        icon = QLabel()
        icon.setPixmap(
            qta.icon("fa5s.calendar-alt", color=NEUTRAL["500"]).pixmap(15, 15)
        )
        layout.addWidget(icon)

        self.date_from = QDateEdit(QDate.currentDate().addDays(-29))
        self.date_from.setObjectName("RangeDate")
        self.date_from.setCalendarPopup(True)
        self.date_from.setDisplayFormat("dd/MM/yyyy")
        layout.addWidget(self.date_from)

        from PySide6.QtWidgets import QApplication

        _app_dir = QApplication.instance()
        _rtl = (
            _app_dir.layoutDirection() == Qt.LayoutDirection.RightToLeft
            if _app_dir
            else False
        )
        arrow_text = "←" if _rtl else "→"
        arrow = QLabel(arrow_text)
        arrow.setObjectName("Muted")
        layout.addWidget(arrow)

        self.date_to = QDateEdit(QDate.currentDate())
        self.date_to.setObjectName("RangeDate")
        self.date_to.setCalendarPopup(True)
        self.date_to.setDisplayFormat("dd/MM/yyyy")
        layout.addWidget(self.date_to)

        self.date_from.dateChanged.connect(self._on_manual_date)
        self.date_to.dateChanged.connect(self._on_manual_date)
        return box

    def _make_tabs(self, items, current, on_select):
        """A small segmented control (reuses the preset pill styling)."""
        group = QWidget()
        group.setObjectName("SegmentGroup")
        group.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QHBoxLayout(group)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(3)
        button_group = QButtonGroup(group)
        button_group.setExclusive(True)
        buttons = {}
        for key, label in items:
            button = QPushButton(label)
            button.setObjectName("SegmentPill")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _=False, k=key: on_select(k))
            button_group.addButton(button)
            layout.addWidget(button)
            buttons[key] = button
        buttons[current].setChecked(True)
        return group

    def _apply_preset(self, key: str) -> None:
        today = QDate.currentDate()
        starts = {
            "today": today,
            "7d": today.addDays(-6),
            "30d": today.addDays(-29),
            "month": QDate(today.year(), today.month(), 1),
            "year": QDate(today.year(), 1, 1),
        }
        self._suppress_manual = True
        self.date_from.setDate(starts.get(key, today.addDays(-29)))
        self.date_to.setDate(today)
        self._suppress_manual = False
        self.refresh()

    def _on_manual_date(self, _date: QDate) -> None:
        if getattr(self, "_suppress_manual", False):
            return
        self._preset_group.setExclusive(False)
        checked = self._preset_group.checkedButton()
        if checked is not None:
            checked.setChecked(False)
        self._preset_group.setExclusive(True)

    def _build_kpi_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(SPACING["md"])
        self.kpi_revenue = KpiCard(
            strings.STATS_REVENUE, "fa5s.coins", *_KPI_BLUE, show_delta=True
        )
        self.kpi_profit = KpiCard(
            strings.STATS_PROFIT, "fa5s.chart-line", *_KPI_GREEN, show_delta=True
        )
        self.kpi_sales = KpiCard(
            strings.STATS_SALES_COUNT, "fa5s.receipt", *_KPI_VIOLET, show_delta=True
        )
        self.kpi_discount = KpiCard(
            strings.STATS_DISCOUNTS, "fa5s.tag", *_KPI_AMBER, show_delta=True
        )
        for card in (
            self.kpi_revenue,
            self.kpi_profit,
            self.kpi_sales,
            self.kpi_discount,
        ):
            row.addWidget(card, stretch=1)
        return row

    def _build_trend(self) -> QWidget:
        card = SectionCard(strings.STATS_TREND_TITLE, "fa5s.chart-area")
        self.line_chart = LineChart()
        self.line_chart.setMinimumHeight(240)
        card.body.addWidget(self.line_chart)
        return card

    def _build_snapshot_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(SPACING["md"])
        self.snap_stock = KpiCard(strings.STATS_STOCK_VALUE, "fa5s.boxes", *_KPI_BLUE)
        self.snap_credit = KpiCard(
            strings.STATS_CUSTOMER_CREDIT, "fa5s.hand-holding-usd", *_KPI_AMBER
        )
        self.snap_supplier = KpiCard(
            strings.STATS_SUPPLIER_DEBT, "fa5s.truck", *_KPI_VIOLET
        )
        self.snap_rupture = KpiCard(
            strings.STATS_OUT_OF_STOCK, "fa5s.exclamation-triangle", *_KPI_RED
        )
        for card in (
            self.snap_stock,
            self.snap_credit,
            self.snap_supplier,
            self.snap_rupture,
        ):
            row.addWidget(card, stretch=1)
        return row

    def _build_products_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(SPACING["md"])

        top_card = SectionCard(strings.STATS_TOP_PRODUCTS, "fa5s.crown")
        top_card.header.addWidget(
            self._make_tabs(
                [
                    ("quantity", strings.STATS_SORT_QTY),
                    ("profit", strings.STATS_SORT_PROFIT),
                ],
                self._top_sort,
                self._set_top_sort,
            )
        )
        self.top_table = DataTable(
            [
                "",
                strings.STATS_COL_PRODUCT,
                strings.STATS_COL_QTY,
                strings.STATS_COL_REVENUE,
                strings.STATS_COL_MARGIN,
            ]
        )
        self.top_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Fixed
        )
        self.top_table.setColumnWidth(0, THUMB_SIZES["table"] + 14)
        self.top_table.verticalHeader().setDefaultSectionSize(THUMB_SIZES["table"] + 10)
        self.top_stack = StatefulStack(
            self.top_table,
            EmptyState("fa5s.crown", strings.STATS_NO_DATA),
        )
        self.top_stack.setMinimumHeight(280)
        top_card.body.addWidget(self.top_stack)
        row.addWidget(top_card, stretch=3)

        cat_card = SectionCard(strings.STATS_CATEGORY_TITLE, "fa5s.layer-group")
        self.cat_donut = DonutChart()
        self.cat_donut.setMinimumHeight(240)
        cat_card.body.addWidget(self.cat_donut)
        row.addWidget(cat_card, stretch=2)
        return row

    def _build_patterns_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(SPACING["md"])

        busy_card = SectionCard(strings.STATS_BUSY_TITLE, "fa5s.clock")
        busy_card.header.addWidget(
            self._make_tabs(
                [
                    ("hours", strings.STATS_BUSY_HOURS),
                    ("days", strings.STATS_BUSY_DAYS),
                ],
                self._busy_mode,
                self._set_busy_mode,
            )
        )
        self.busy_chart = ColumnChart()
        self.busy_chart.setMinimumHeight(200)
        busy_card.body.addWidget(self.busy_chart)
        row.addWidget(busy_card, stretch=1)

        cust_card = SectionCard(strings.STATS_TOP_CUSTOMERS, "fa5s.user-friends")
        self.cust_table = DataTable(
            [
                strings.STATS_COL_CUSTOMER,
                strings.STATS_COL_PURCHASES,
                strings.STATS_COL_REVENUE,
            ]
        )
        self.cust_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        for col in (1, 2):
            self.cust_table.horizontalHeader().setSectionResizeMode(
                col, QHeaderView.ResizeMode.ResizeToContents
            )
        self.cust_stack = StatefulStack(
            self.cust_table,
            EmptyState("fa5s.user-friends", strings.STATS_CUSTOMERS_EMPTY),
        )
        self.cust_stack.setMinimumHeight(200)
        cust_card.body.addWidget(self.cust_stack)
        row.addWidget(cust_card, stretch=1)
        return row

    def _build_lower_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(SPACING["md"])

        dead_card = SectionCard(strings.STATS_DEAD_STOCK_TITLE, "fa5s.hourglass-half")
        dead_card.header.addWidget(
            self._make_tabs(
                [
                    ("30", strings.STATS_DEAD_30),
                    ("60", strings.STATS_DEAD_60),
                    ("90", strings.STATS_DEAD_90),
                ],
                str(self._dead_days),
                self._set_dead_days,
            )
        )
        self.dead_table = DataTable(
            [
                strings.STATS_COL_PRODUCT,
                strings.STATS_COL_STOCK,
                strings.STATS_COL_TIED,
                strings.STATS_COL_LAST_SALE,
            ]
        )
        self.dead_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        for col in (1, 2, 3):
            self.dead_table.horizontalHeader().setSectionResizeMode(
                col, QHeaderView.ResizeMode.ResizeToContents
            )
        self.dead_stack = StatefulStack(
            self.dead_table,
            EmptyState("fa5s.hourglass-half", strings.STATS_DEAD_STOCK_EMPTY),
        )
        self.dead_stack.setMinimumHeight(200)
        dead_card.body.addWidget(self.dead_stack)
        row.addWidget(dead_card, stretch=1)

        margin_card = SectionCard(
            strings.STATS_CATEGORY_MARGIN_TITLE, "fa5s.percentage"
        )
        self.cat_bars = RankBars()
        margin_card.body.addWidget(self.cat_bars)
        margin_card.body.addStretch(1)
        row.addWidget(margin_card, stretch=1)
        return row

    def _build_associations(self) -> QWidget:
        assoc_card = SectionCard(strings.STATS_ASSOCIATIONS, "fa5s.link")
        self.rules_holder = QWidget()
        self.rules_layout = QVBoxLayout(self.rules_holder)
        self.rules_layout.setContentsMargins(0, 0, 0, 0)
        self.rules_layout.setSpacing(SPACING["sm"])
        self.assoc_stack = StatefulStack(
            self.rules_holder,
            EmptyState(
                "fa5s.link",
                strings.STATS_ASSOCIATIONS_EMPTY,
                strings.STATS_ASSOCIATIONS_EMPTY_HINT,
            ),
        )
        self.assoc_stack.setMinimumHeight(160)
        assoc_card.body.addWidget(self.assoc_stack)
        return assoc_card

    # ---------------------------------------------------------- toggles

    def _set_top_sort(self, sort: str) -> None:
        self._top_sort = sort
        date_from, date_to = self._range()
        self.top_stack.show_loading()
        run_api(
            lambda: self.api.stats_top_products(
                self.store_id, date_from, date_to, sort=sort
            ),
            self._on_top,
            self._on_error,
        )

    def _set_dead_days(self, days: str) -> None:
        self._dead_days = int(days)
        self.dead_stack.show_loading()
        run_api(
            lambda: self.api.stats_dead_stock(self.store_id, days=self._dead_days),
            self._on_dead,
            self._on_error,
        )

    def _set_busy_mode(self, mode: str) -> None:
        self._busy_mode = mode
        self._render_busy()

    # ------------------------------------------------------------- loading

    def _range(self) -> tuple[str, str]:
        return (
            self.date_from.date().toString("yyyy-MM-dd"),
            self.date_to.date().toString("yyyy-MM-dd"),
        )

    def _prev_range(self) -> tuple[str, str]:
        """The equal-length window immediately before the current one."""
        d_from = self.date_from.date()
        d_to = self.date_to.date()
        length = d_from.daysTo(d_to) + 1
        prev_to = d_from.addDays(-1)
        prev_from = prev_to.addDays(-(length - 1))
        return (
            prev_from.toString("yyyy-MM-dd"),
            prev_to.toString("yyyy-MM-dd"),
        )

    def export_pdf(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Enregistrer le rapport", "rapport.pdf", "PDF (*.pdf)"
        )
        if not path:
            return
        df, dt = self._range()
        run_api(
            lambda: self.api.get_report_pdf(self.store_id, df, dt),
            lambda data: self._save_file(path, data),
            lambda err: show_error(self, strings.ERROR_TITLE, err.message),
        )

    def export_xlsx(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Enregistrer le rapport", "rapport.xlsx", "Excel (*.xlsx)"
        )
        if not path:
            return
        df, dt = self._range()
        run_api(
            lambda: self.api.get_report_xlsx(self.store_id, df, dt),
            lambda data: self._save_file(path, data),
            lambda err: show_error(self, strings.ERROR_TITLE, err.message),
        )

    def _save_file(self, path: str, data: bytes) -> None:
        try:
            with open(path, "wb") as f:
                f.write(data)
        except OSError as e:
            show_error(self, strings.ERROR_TITLE, f"Erreur d'écriture : {e}")

    def _daily_report(self) -> None:
        """Pick a past date, then generate + open the end-of-day PDF."""
        picker = _DailyReportDatePicker(self)
        if not picker.exec() or picker.selected is None:
            return
        day = picker.selected.toString("yyyy-MM-dd")
        run_api(
            lambda: self.api.get_daily_report_pdf(self.store_id, day),
            lambda pdf: self._open_daily_report(day, pdf),
            lambda err: show_error(self, err.message),
        )

    def _open_daily_report(self, day: str, pdf: bytes) -> None:
        from services import printing

        path = Path(tempfile.gettempdir()) / f"rapport_journalier_{day}.pdf"
        try:
            path.write_bytes(pdf)
            printing.open_file(path)
        except OSError as exc:
            show_error(self, strings.OPEN_PDF_FAILED.format(path=exc))

    def refresh(self) -> None:
        date_from, date_to = self._range()
        prev_from, prev_to = self._prev_range()
        self._error_shown = False
        self._cur_summary = None
        self._prev_summary = None

        self.top_stack.show_loading()
        self.cust_stack.show_loading()
        self.dead_stack.show_loading()
        self.assoc_stack.show_loading()

        run_api(
            lambda: self.api.list_products(self.store_id),
            self._on_products,
            lambda err: None,  # thumbnails only; tables still render
        )
        run_api(
            lambda: self.api.stats_summary(self.store_id, date_from, date_to),
            self._on_summary,
            self._on_error,
        )
        run_api(
            lambda: self.api.stats_summary(self.store_id, prev_from, prev_to),
            self._on_prev_summary,
            lambda err: None,  # comparison is best-effort
        )
        run_api(
            lambda: self.api.stats_daily_evolution(self.store_id, date_from, date_to),
            self._on_evolution,
            self._on_error,
        )
        run_api(
            lambda: self.api.stats_top_products(
                self.store_id, date_from, date_to, sort=self._top_sort
            ),
            self._on_top,
            self._on_error,
        )
        run_api(
            lambda: self.api.stats_category_breakdown(
                self.store_id, date_from, date_to
            ),
            self._on_categories,
            self._on_error,
        )
        run_api(
            lambda: self.api.stats_sales_patterns(self.store_id, date_from, date_to),
            self._on_patterns,
            self._on_error,
        )
        run_api(
            lambda: self.api.stats_top_customers(self.store_id, date_from, date_to),
            self._on_customers,
            self._on_error,
        )
        run_api(
            lambda: self.api.stats_customer_insights(self.store_id, date_from, date_to),
            self._on_customer_insights,
            lambda err: None,  # a KPI subline only
        )
        run_api(
            lambda: self.api.stats_inventory(self.store_id),
            self._on_inventory,
            self._on_error,
        )
        run_api(
            lambda: self.api.stats_financial_snapshot(self.store_id),
            self._on_financial,
            self._on_error,
        )
        run_api(
            lambda: self.api.stats_dead_stock(self.store_id, days=self._dead_days),
            self._on_dead,
            self._on_error,
        )
        run_api(
            lambda: self.api.stats_associations(self.store_id, date_from, date_to),
            self._on_associations,
            self._on_assoc_error,
        )

    # ------------------------------------------------------------ handlers

    def _on_products(self, products_page: dict) -> None:
        items = products_page.get("items", []) if isinstance(products_page, dict) else []
        self.products_by_id = {p["id"]: p for p in items}
        if self._top_data:
            self._render_top_thumbs(self._top_data)

    def _on_summary(self, summary: object) -> None:
        self._cur_summary = summary
        revenue = Decimal(str(summary.get("revenue", 0)))
        profit = Decimal(str(summary.get("gross_profit", 0)))
        count = int(summary.get("sales_count", 0))
        discounts = Decimal(str(summary.get("total_discounts", 0)))

        basket = (revenue / count) if count else Decimal("0")
        self.kpi_revenue.set_value(
            fmt.fmt_money(revenue),
            sub=f"{strings.STATS_AVG_BASKET} : {fmt.fmt_money(basket)}",
        )

        margin = (profit / revenue) if revenue else Decimal("0")
        tone = "success" if profit > 0 else ("danger" if profit < 0 else "")
        self.kpi_profit.set_value(
            fmt.fmt_money(profit),
            sub=f"{strings.STATS_MARGIN} : {fmt.fmt_percent(float(margin))}",
            tone=tone,
        )

        self._render_sales_card()

        discount_share = (discounts / revenue) if revenue else Decimal("0")
        self.kpi_discount.set_value(
            fmt.fmt_money(discounts),
            sub=f"{fmt.fmt_percent(float(discount_share))} {strings.STATS_OF_REVENUE}",
        )
        self._apply_deltas()

    def _on_prev_summary(self, summary: object) -> None:
        self._prev_summary = summary
        self._apply_deltas()

    def _apply_deltas(self) -> None:
        if self._cur_summary is None or self._prev_summary is None:
            return
        cur, prev = self._cur_summary, self._prev_summary
        self.kpi_revenue.set_delta(
            Decimal(str(cur["revenue"])), Decimal(str(prev["revenue"]))
        )
        self.kpi_profit.set_delta(
            Decimal(str(cur["gross_profit"])), Decimal(str(prev["gross_profit"]))
        )
        self.kpi_sales.set_delta(
            Decimal(int(cur["sales_count"])), Decimal(int(prev["sales_count"]))
        )
        self.kpi_discount.set_delta(
            Decimal(str(cur["total_discounts"])), Decimal(str(prev["total_discounts"]))
        )

    def _render_sales_card(self) -> None:
        if self._cur_summary is None:
            return
        count = int(self._cur_summary.get("sales_count", 0))
        sub = ""
        if self._insights is not None:
            sub = strings.STATS_CUSTOMERS_SUB.format(
                active=self._insights.get("active_customers", 0),
                new=self._insights.get("new_customers", 0),
            )
        self.kpi_sales.set_value(str(count), sub=sub)

    def _on_customer_insights(self, insights: object) -> None:
        self._insights = insights
        self._render_sales_card()

    def _on_evolution(self, points: object) -> None:
        series = [
            LinePoint(
                day=date.fromisoformat(p["day"]),
                revenue=Decimal(str(p["revenue"])),
                profit=Decimal(str(p["profit"])),
            )
            for p in points
        ]
        self.line_chart.set_data(series)

    def _on_top(self, top: object) -> None:
        top = list(top)
        self._top_data = top
        if not top:
            self.top_stack.show_empty()
            return
        self.top_table.set_rows(
            [
                [
                    "",
                    t["name"],
                    t["quantity_sold"],
                    fmt.fmt_money(t["revenue"]),
                    self._margin_text(t),
                ]
                for t in top
            ]
        )
        self._render_top_thumbs(top)
        self.top_stack.show_content()

    def _margin_text(self, entry: dict) -> str:
        revenue = Decimal(str(entry.get("revenue", 0)))
        profit = Decimal(str(entry.get("profit", 0)))
        if revenue <= 0:
            return "—"
        return fmt.fmt_percent(float(profit / revenue))

    def _render_top_thumbs(self, top: list) -> None:
        for row, entry in enumerate(top):
            product = self.products_by_id.get(entry["product_id"])
            thumb = Thumb(THUMB_SIZES["table"])
            if product:
                thumb.set_product(product)
            else:
                thumb.set_letter(entry["name"])
            holder = QWidget()
            holder_layout = QHBoxLayout(holder)
            holder_layout.setContentsMargins(4, 2, 4, 2)
            holder_layout.addWidget(thumb, alignment=Qt.AlignmentFlag.AlignCenter)
            self.top_table.setCellWidget(row, 0, holder)

    def _on_categories(self, cats: object) -> None:
        self._categories = list(cats)
        self._render_categories()

    def _render_categories(self) -> None:
        cats = self._categories or []
        ranked = sorted(cats, key=lambda c: Decimal(str(c["revenue"])), reverse=True)
        items = [
            (c["name"] or strings.STATS_NO_CATEGORY, Decimal(str(c["revenue"])))
            for c in ranked[:6]
        ]
        rest = ranked[6:]
        if rest:
            other = sum((Decimal(str(c["revenue"])) for c in rest), Decimal("0"))
            if other > 0:
                items.append((strings.STATS_OTHERS, other))
        self.cat_donut.set_items(items)

        shown = ranked[:6]
        margins = []
        for c in shown:
            revenue = Decimal(str(c["revenue"]))
            profit = Decimal(str(c["profit"]))
            margins.append(float(profit / revenue) if revenue > 0 else 0.0)
        max_margin = max(margins, default=0.0) or 1.0
        rows = []
        for index, c in enumerate(shown):
            rows.append(
                (
                    c["name"] or strings.STATS_NO_CATEGORY,
                    fmt.fmt_percent(margins[index]),
                    margins[index] / max_margin,
                    _CAT_PALETTE[index % len(_CAT_PALETTE)],
                )
            )
        self.cat_bars.set_rows(rows)

    def _on_patterns(self, patterns: object) -> None:
        self._patterns = patterns
        self._render_busy()

    def _render_busy(self) -> None:
        if not self._patterns:
            return
        if self._busy_mode == "days":
            bars = [
                (strings.WEEKDAY_SHORT[d["weekday"]], float(d["sales_count"]))
                for d in self._patterns.get("weekday", [])
            ]
        else:
            bars = [
                (
                    strings.STATS_HOUR_LABEL.format(hour=h["hour"]),
                    float(h["sales_count"]),
                )
                for h in self._patterns.get("hourly", [])
            ]
        peak_text = ""
        if bars:
            peak = max(range(len(bars)), key=lambda i: bars[i][1])
            if bars[peak][1] > 0:
                peak_text = bars[peak][0]
        self.busy_chart.set_data(bars, peak_text)

    def _on_customers(self, customers: object) -> None:
        customers = list(customers)
        if not customers:
            self.cust_stack.show_empty()
            return
        self.cust_table.set_rows(
            [
                [
                    c["name"],
                    c["sales_count"],
                    fmt.fmt_money(c["revenue"]),
                ]
                for c in customers
            ]
        )
        self.cust_stack.show_content()

    def _on_inventory(self, inv: object) -> None:
        self.snap_stock.set_value(
            fmt.fmt_money(inv.get("stock_value_cost", 0)),
            sub=strings.STATS_STOCK_VALUE_RETAIL.format(
                value=fmt.fmt_money(inv.get("stock_value_retail", 0))
            ),
        )
        out_of_stock = int(inv.get("out_of_stock_count", 0))
        low_stock = int(inv.get("low_stock_count", 0))
        self.snap_rupture.set_value(
            str(out_of_stock),
            sub=strings.STATS_LOW_STOCK_HINT.format(count=low_stock),
            tone="danger" if out_of_stock > 0 else "",
        )

    def _on_financial(self, fin: object) -> None:
        credit = Decimal(str(fin.get("customer_credit_total", 0)))
        self.snap_credit.set_value(
            fmt.fmt_money(credit),
            sub=strings.STATS_CREDIT_SALES.format(
                count=int(fin.get("customer_credit_count", 0))
            ),
            tone="danger" if credit > 0 else "",
        )
        debt = Decimal(str(fin.get("supplier_debt_total", 0)))
        self.snap_supplier.set_value(
            fmt.fmt_money(debt),
            sub=strings.STATS_SUPPLIER_ORDERS.format(
                count=int(fin.get("supplier_debt_count", 0))
            ),
            tone="danger" if debt > 0 else "",
        )

    def _on_dead(self, items: object) -> None:
        items = list(items)
        if not items:
            self.dead_stack.show_empty()
            return
        rows = []
        for item in items:
            if item["days_since"] is None:
                last = strings.STATS_NEVER_SOLD
            else:
                last = strings.STATS_DAYS_AGO.format(days=item["days_since"])
            rows.append(
                [
                    item["name"],
                    item["stock_quantity"],
                    fmt.fmt_money(item["tied_capital"]),
                    last,
                ]
            )
        self.dead_table.set_rows(rows)
        self.dead_stack.show_content()

    def _on_associations(self, result: object) -> None:
        while self.rules_layout.count():
            item = self.rules_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        rules = result.get("rules", [])
        if not rules:
            self.assoc_stack.show_empty()
            return
        for rule in rules[:12]:
            self.rules_layout.addWidget(RuleCard(rule))
        self.rules_layout.addStretch(1)
        self.assoc_stack.show_content()

    def _on_assoc_error(self, err) -> None:
        self.assoc_stack.show_empty()
        self._on_error(err)

    def _on_error(self, err) -> None:
        if getattr(self, "_error_shown", False):
            return
        self._error_shown = True
        if err.code in ("invalid_pin", "pin_not_configured"):
            show_error(self, strings.STATS_PIN_REQUIRED)
        else:
            show_error(self, err.message)
