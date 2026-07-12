"""Period comparison — a Statistics tab that puts two date ranges side by side.

Pure client-side aggregation over the existing statistics endpoints (called
once per period): a metrics table with % change indicators, a grouped bar
chart of daily revenue for both periods, side-by-side top-5 tables, and a PDF
export of the comparison.
"""

from decimal import Decimal

import qtawesome as qta
import shiboken6
from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from services.workers import run_api
from ui import format as fmt
from ui import strings
from ui.styles.tokens import NEUTRAL, SEMANTIC, SPACING
from ui.widgets.card import SectionCard
from ui.widgets.charts import GroupedBarChart
from ui.widgets.data_table import DataTable
from ui.widgets.modal import show_error
from ui.widgets.toast import show_toast


class _RangeBox(QWidget):
    """A small (Du … au …) date-range picker."""

    def __init__(self, caption: str, default_from: QDate, default_to: QDate) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACING["xs"])
        label = QLabel(caption)
        label.setObjectName("Caption")
        layout.addWidget(label)
        from PySide6.QtWidgets import QDateEdit

        self.date_from = QDateEdit(default_from)
        self.date_from.setCalendarPopup(True)
        self.date_from.setDisplayFormat("dd/MM/yyyy")
        layout.addWidget(self.date_from)
        arrow = QLabel("→")
        arrow.setObjectName("Muted")
        layout.addWidget(arrow)
        self.date_to = QDateEdit(default_to)
        self.date_to.setCalendarPopup(True)
        self.date_to.setDisplayFormat("dd/MM/yyyy")
        layout.addWidget(self.date_to)

    def range(self) -> tuple[str, str]:
        return (
            self.date_from.date().toString("yyyy-MM-dd"),
            self.date_to.date().toString("yyyy-MM-dd"),
        )

    def set_range(self, start: QDate, end: QDate) -> None:
        self.date_from.setDate(start)
        self.date_to.setDate(end)


class PeriodComparisonTab(QWidget):
    def __init__(self, api, store_id: str, parent=None) -> None:
        super().__init__(parent)
        self.api = api
        self.store_id = store_id
        self._a: dict = {}
        self._b: dict = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACING["md"])

        today = QDate.currentDate()
        month_start = QDate(today.year(), today.month(), 1)
        prev_month_end = month_start.addDays(-1)
        prev_month_start = QDate(prev_month_end.year(), prev_month_end.month(), 1)
        self.range_a = _RangeBox(strings.CMP_PERIOD_A, month_start, today)
        self.range_b = _RangeBox(strings.CMP_PERIOD_B, prev_month_start, prev_month_end)

        # Presets + ranges + actions.
        controls = QHBoxLayout()
        for key, label in (
            ("month", strings.CMP_PRESET_MONTH),
            ("quarter", strings.CMP_PRESET_QUARTER),
            ("year", strings.CMP_PRESET_YEAR),
        ):
            button = QPushButton(label)
            button.setObjectName("Secondary")
            button.clicked.connect(lambda _=False, k=key: self._apply_preset(k))
            controls.addWidget(button)
        controls.addStretch(1)
        compare = QPushButton(strings.CMP_COMPARE)
        compare.setObjectName("Primary")
        compare.clicked.connect(self.refresh)
        controls.addWidget(compare)
        self.export_button = QPushButton(strings.STATS_EXPORT_PDF)
        self.export_button.setObjectName("Secondary")
        self.export_button.clicked.connect(self._export_pdf)
        controls.addWidget(self.export_button)

        ranges = QHBoxLayout()
        ranges.addWidget(self.range_a)
        ranges.addStretch(1)
        ranges.addWidget(self.range_b)
        layout.addLayout(ranges)
        layout.addLayout(controls)

        # Comparison table.
        table_card = SectionCard(strings.CMP_TABLE_TITLE, "fa5s.balance-scale")
        self.table = DataTable(
            [
                strings.CMP_COL_METRIC,
                strings.CMP_PERIOD_A,
                strings.CMP_PERIOD_B,
                strings.CMP_COL_CHANGE,
            ]
        )
        self.table.setMinimumHeight(240)
        table_card.body.addWidget(self.table)
        layout.addWidget(table_card)

        # Grouped bar chart.
        chart_card = SectionCard(strings.CMP_CHART_TITLE, "fa5s.chart-bar")
        self.chart = GroupedBarChart()
        self.chart.setMinimumHeight(220)
        chart_card.body.addWidget(self.chart)
        layout.addWidget(chart_card)

        # Side-by-side top-5 tables.
        tops = QHBoxLayout()
        tops.setSpacing(SPACING["md"])
        top_a_card = SectionCard(
            f"{strings.CMP_PERIOD_A} — {strings.STATS_TOP_PRODUCTS}", "fa5s.crown"
        )
        self.top_a_table = DataTable(
            [
                strings.STATS_COL_PRODUCT,
                strings.STATS_COL_QTY,
                strings.STATS_COL_REVENUE,
            ]
        )
        top_a_card.body.addWidget(self.top_a_table)
        tops.addWidget(top_a_card, stretch=1)
        top_b_card = SectionCard(
            f"{strings.CMP_PERIOD_B} — {strings.STATS_TOP_PRODUCTS}", "fa5s.crown"
        )
        self.top_b_table = DataTable(
            [
                strings.STATS_COL_PRODUCT,
                strings.STATS_COL_QTY,
                strings.STATS_COL_REVENUE,
            ]
        )
        top_b_card.body.addWidget(self.top_b_table)
        tops.addWidget(top_b_card, stretch=1)
        layout.addLayout(tops)
        layout.addStretch(1)

    # --------------------------------------------------------------- presets

    def _apply_preset(self, key: str) -> None:
        today = QDate.currentDate()
        if key == "month":
            a_start = QDate(today.year(), today.month(), 1)
            a_end = today
            b_end = a_start.addDays(-1)
            b_start = QDate(b_end.year(), b_end.month(), 1)
        elif key == "quarter":
            q = (today.month() - 1) // 3
            a_start = QDate(today.year(), q * 3 + 1, 1)
            a_end = today
            b_end = a_start.addDays(-1)
            b_start = b_end.addMonths(-2)
            b_start = QDate(b_start.year(), b_start.month(), 1)
        else:  # year
            a_start = QDate(today.year(), 1, 1)
            a_end = today
            b_start = QDate(today.year() - 1, 1, 1)
            b_end = QDate(today.year() - 1, 12, 31)
        self.range_a.set_range(a_start, a_end)
        self.range_b.set_range(b_start, b_end)
        self.refresh()

    # --------------------------------------------------------------- loading

    def refresh(self) -> None:
        self._a = {}
        self._b = {}
        a_from, a_to = self.range_a.range()
        b_from, b_to = self.range_b.range()
        for side, (df, dt) in (("a", (a_from, a_to)), ("b", (b_from, b_to))):
            run_api(
                lambda df=df, dt=dt: self.api.stats_summary(self.store_id, df, dt),
                lambda r, s=side: self._store(s, "summary", r),
                self._on_error,
            )
            run_api(
                lambda df=df, dt=dt: self.api.stats_customer_insights(
                    self.store_id, df, dt
                ),
                lambda r, s=side: self._store(s, "insights", r),
                lambda err: None,
            )
            run_api(
                lambda df=df, dt=dt: self.api.stats_category_breakdown(
                    self.store_id, df, dt
                ),
                lambda r, s=side: self._store(s, "cats", r),
                lambda err: None,
            )
            run_api(
                lambda df=df, dt=dt: self.api.stats_top_products(
                    self.store_id, df, dt, limit=5
                ),
                lambda r, s=side: self._store(s, "top", r),
                lambda err: None,
            )
            run_api(
                lambda df=df, dt=dt: self.api.stats_daily_evolution(
                    self.store_id, df, dt
                ),
                lambda r, s=side: self._store(s, "evolution", r),
                lambda err: None,
            )

    def _store(self, side: str, key: str, value: object) -> None:
        if not shiboken6.isValid(self):
            return
        (self._a if side == "a" else self._b)[key] = value
        self._render()

    def _on_error(self, err) -> None:
        if not shiboken6.isValid(self):
            return
        if err.code in ("invalid_pin", "pin_not_configured"):
            show_error(self, strings.STATS_PIN_REQUIRED)
        else:
            show_error(self, err.message)

    # --------------------------------------------------------------- render

    def _render(self) -> None:
        self._render_table()
        self._render_chart()
        self._render_tops()

    @staticmethod
    def _dec(value) -> Decimal:
        try:
            return Decimal(str(value))
        except (TypeError, ArithmeticError, ValueError):
            return Decimal("0")

    def _metric_values(self, data: dict) -> dict:
        summary = data.get("summary") or {}
        revenue = self._dec(summary.get("revenue", 0))
        sales = int(summary.get("sales_count", 0) or 0)
        cats = data.get("cats") or []
        top_cat = max(
            (self._dec(c.get("revenue", 0)) for c in cats), default=Decimal("0")
        )
        return {
            "revenue": revenue,
            "profit": self._dec(summary.get("gross_profit", 0)),
            "sales": Decimal(sales),
            "basket": (revenue / sales) if sales else Decimal("0"),
            "customers": Decimal(
                int((data.get("insights") or {}).get("active_customers", 0) or 0)
            ),
            "top_cat": top_cat,
        }

    def _render_table(self) -> None:
        if "summary" not in self._a or "summary" not in self._b:
            return
        a = self._metric_values(self._a)
        b = self._metric_values(self._b)
        rows = [
            (strings.CMP_METRIC_REVENUE, a["revenue"], b["revenue"], True),
            (strings.CMP_METRIC_PROFIT, a["profit"], b["profit"], True),
            (strings.CMP_METRIC_SALES, a["sales"], b["sales"], False),
            (strings.CMP_METRIC_BASKET, a["basket"], b["basket"], True),
            (strings.CMP_METRIC_CUSTOMERS, a["customers"], b["customers"], False),
            (strings.CMP_METRIC_TOP_CATEGORY, a["top_cat"], b["top_cat"], True),
        ]
        self.table.set_rows(
            [
                [
                    label,
                    fmt.fmt_money(av) if money else str(int(av)),
                    fmt.fmt_money(bv) if money else str(int(bv)),
                    "",  # change widget
                ]
                for label, av, bv, money in rows
            ]
        )
        for row, (_label, av, bv, _money) in enumerate(rows):
            self.table.setCellWidget(row, 3, self._change_cell(av, bv))

    def _change_cell(self, a: Decimal, b: Decimal) -> QWidget:
        holder = QWidget()
        box = QHBoxLayout(holder)
        box.setContentsMargins(SPACING["xs"], 2, SPACING["xs"], 2)
        box.setSpacing(2)
        if b == 0:
            text, color, icon = ("—", NEUTRAL["500"], None)
            if a > 0:
                text, color, icon = ("+100 %", SEMANTIC["success"], "fa5s.arrow-up")
        else:
            pct = (a - b) / b * 100
            up = pct >= 0
            color = SEMANTIC["success"] if up else SEMANTIC["danger"]
            icon = "fa5s.arrow-up" if up else "fa5s.arrow-down"
            text = f"{'+' if up else ''}{pct:.0f} %"
        if icon:
            from ui.styles.tokens import ICON_SIZES

            arrow = QLabel()
            arrow.setPixmap(
                qta.icon(icon, color=color).pixmap(ICON_SIZES["sm"], ICON_SIZES["sm"])
            )
            arrow.setStyleSheet("background: transparent;")
            box.addWidget(arrow)
        label = QLabel(text)
        label.setStyleSheet(
            f"color: {color}; font-weight: 700; background: transparent;"
        )
        box.addWidget(label)
        box.addStretch(1)
        return holder

    def _render_chart(self) -> None:
        ev_a = self._a.get("evolution")
        ev_b = self._b.get("evolution")
        if ev_a is None or ev_b is None:
            return
        series_a = [float(self._dec(p.get("revenue", 0))) for p in ev_a]
        series_b = [float(self._dec(p.get("revenue", 0))) for p in ev_b]
        length = max(len(series_a), len(series_b))
        series_a += [0.0] * (length - len(series_a))
        series_b += [0.0] * (length - len(series_b))
        labels = [str(i + 1) for i in range(length)]
        self.chart.set_data(
            labels, series_a, series_b, strings.CMP_PERIOD_A, strings.CMP_PERIOD_B
        )

    def _render_tops(self) -> None:
        for data, table in ((self._a, self.top_a_table), (self._b, self.top_b_table)):
            top = data.get("top")
            if top is None:
                continue
            table.set_rows(
                [
                    [t["name"], t["quantity_sold"], fmt.fmt_money(t["revenue"])]
                    for t in top
                ]
            )

    # --------------------------------------------------------------- export

    def _export_pdf(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, strings.STATS_EXPORT_PDF, "comparaison.pdf", "PDF (*.pdf)"
        )
        if not path:
            return
        a_from, a_to = self.range_a.range()
        b_from, b_to = self.range_b.range()
        run_api(
            lambda: self.api.get_comparison_report_pdf(
                self.store_id, a_from, a_to, b_from, b_to
            ),
            lambda data: self._save(path, data),
            self._on_error,
        )

    def _save(self, path: str, data: bytes) -> None:
        from pathlib import Path

        try:
            Path(path).write_bytes(data)
            show_toast(self, strings.EXPORT_SAVED_TOAST.format(path=path))
        except OSError as exc:
            show_error(self, str(exc))
