"""Statistiques — a modern activity dashboard.

Range-driven headline KPIs (chiffre d'affaires, bénéfice, ventes, remises)
with derived insight sublines (panier moyen, marge, % du CA); a per-period
evolution strip comparing today / semaine / mois / année with the previous
period; the best sellers; the payment-method split as a proportional share
bar; and the market-basket association rules ("souvent achetés ensemble").

All statistics endpoints are owner data (they derive from cost_price): the
API requires the PIN, which the client sends automatically when it was
captured at login.
"""

from decimal import Decimal

import qtawesome as qta
from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QDateEdit,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from services.workers import run_api
from ui import format as fmt
from ui import strings
from ui.styles.tokens import ICON_SIZES, RADIUS, SPACING, THUMB_SIZES
from ui.widgets.badge import DeltaChip
from ui.widgets.card import Card, SectionCard
from ui.widgets.data_table import DataTable
from ui.widgets.modal import show_error
from ui.widgets.states import EmptyState, StatefulStack
from ui.widgets.thumb import Thumb

# Fixed, cheerful icon-chip palette for the KPI cards (foreground, tint).
# Decorative only — kept out of the themeable accent tokens on purpose so the
# dashboard stays colourful whatever accent the owner picks.
_KPI_BLUE = ("#2563EB", "#DBEAFE")
_KPI_GREEN = ("#16A34A", "#DCFCE7")
_KPI_VIOLET = ("#7C3AED", "#EDE9FE")
_KPI_AMBER = ("#D97706", "#FEF3C7")

# Payment-share segment colours (cycled by order).
_PM_PALETTE = ["#2563EB", "#16A34A", "#D97706", "#7C3AED", "#0D9488", "#DB2777"]


class KpiCard(Card):
    """Headline metric: colored icon chip + caption, big value, insight line."""

    def __init__(
        self, caption: str, icon: str, color: str, bg: str, parent=None
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
        chip.setStyleSheet(f"background: {bg}; border-radius: {RADIUS['md']}px;")
        top.addWidget(chip)
        caption_label = QLabel(caption)
        caption_label.setObjectName("StatCardTitle")
        caption_label.setWordWrap(True)
        top.addWidget(caption_label, 1)
        self.body.addLayout(top)

        self.value = QLabel("—")
        self.value.setObjectName("StatCardValue")
        self.value.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.body.addWidget(self.value)

        self.sub = QLabel("")
        self.sub.setObjectName("Muted")
        self.sub.setVisible(False)
        self.body.addWidget(self.sub)
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


class PeriodCard(Card):
    """One calendar period: revenue + delta vs previous, profit/sales subline."""

    def __init__(self, title: str, parent=None) -> None:
        super().__init__(parent)
        caption = QLabel(title.upper())
        caption.setObjectName("StatCardTitle")
        self.body.addWidget(caption)

        row = QHBoxLayout()
        row.setSpacing(SPACING["sm"])
        self.revenue = QLabel("—")
        self.revenue.setObjectName("PeriodRevenue")
        row.addWidget(self.revenue)
        row.addStretch(1)
        self.delta = DeltaChip()
        self.delta.setToolTip(strings.STATS_VS_PREVIOUS)
        row.addWidget(self.delta, alignment=Qt.AlignmentFlag.AlignVCenter)
        self.body.addLayout(row)

        self.sub = QLabel("—")
        self.sub.setObjectName("Muted")
        self.body.addWidget(self.sub)
        self.body.addStretch(1)

    def set_period(self, period: dict) -> None:
        current, previous = period["current"], period["previous"]
        self.revenue.setText(fmt.fmt_money(current["revenue"]))
        self.delta.set_delta(
            Decimal(str(current["revenue"])), Decimal(str(previous["revenue"]))
        )
        self.sub.setText(
            strings.STATS_PERIOD_SUB.format(
                profit=fmt.fmt_money(current["gross_profit"]),
                count=current["sales_count"],
            )
        )


class PaymentShareBar(QWidget):
    """Payment-method split: one proportional stacked bar + a legend."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(SPACING["md"])

        self._bar_holder = QWidget()
        self._bar = QHBoxLayout(self._bar_holder)
        self._bar.setContentsMargins(0, 0, 0, 0)
        self._bar.setSpacing(2)
        self._bar_holder.setFixedHeight(16)
        outer.addWidget(self._bar_holder)

        self._legend = QVBoxLayout()
        self._legend.setSpacing(SPACING["sm"])
        outer.addLayout(self._legend)

        self._empty = QLabel(strings.STATS_NO_DATA)
        self._empty.setObjectName("Muted")
        outer.addWidget(self._empty)
        outer.addStretch(1)

    def _clear(self) -> None:
        while self._bar.count():
            widget = self._bar.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()
        while self._legend.count():
            widget = self._legend.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()

    def set_data(self, methods: object) -> None:
        self._clear()
        methods = list(methods or [])
        total = sum((Decimal(str(m["total"])) for m in methods), Decimal("0"))
        if not methods or total <= 0:
            self._bar_holder.setVisible(False)
            self._empty.setVisible(True)
            return
        self._bar_holder.setVisible(True)
        self._empty.setVisible(False)

        for index, method in enumerate(methods):
            color = _PM_PALETTE[index % len(_PM_PALETTE)]
            amount = Decimal(str(method["total"]))
            share = amount / total

            segment = QFrame()
            segment.setStyleSheet(f"background: {color}; border-radius: 3px;")
            self._bar.addWidget(segment, max(1, int(share * 1000)))

            label = strings.PAYMENT_METHOD_LABELS.get(
                method["payment_method"], method["payment_method"]
            )
            self._legend.addWidget(
                self._legend_row(
                    color,
                    label,
                    fmt.fmt_money(amount),
                    int(method["count"]),
                    fmt.fmt_percent(float(share)),
                )
            )

    def _legend_row(
        self, color: str, label: str, amount: str, count: int, pct: str
    ) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACING["sm"])
        dot = QLabel()
        dot.setFixedSize(10, 10)
        dot.setStyleSheet(f"background: {color}; border-radius: 5px;")
        layout.addWidget(dot, alignment=Qt.AlignmentFlag.AlignVCenter)
        name = QLabel(label)
        name.setStyleSheet("font-weight: 600; background: transparent;")
        layout.addWidget(name)
        layout.addStretch(1)
        detail = QLabel(f"{amount}  ·  {count}")
        detail.setObjectName("Muted")
        layout.addWidget(detail)
        percent = QLabel(pct)
        percent.setStyleSheet("font-weight: 700; background: transparent;")
        percent.setFixedWidth(48)
        percent.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        layout.addWidget(percent)
        return row


class RuleCard(QWidget):
    """Readable French association rule with its numbers."""

    def __init__(self, rule: dict, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("RuleCard")
        # QWidget subclass: required for the QSS card background/border.
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


class StatisticsScreen(QWidget):
    def __init__(self, api, store_id: str, parent=None) -> None:
        super().__init__(parent)
        self.api = api
        self.store_id = store_id
        self.products_by_id: dict[str, dict] = {}

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
        layout.addWidget(self._section_heading(strings.STATS_EVOLUTION))
        layout.addLayout(self._build_period_row())
        layout.addLayout(self._build_mid_row())
        layout.addWidget(self._build_associations())
        layout.addStretch(1)

        scroll.setWidget(content)
        outer.addWidget(scroll, stretch=1)

    # --------------------------------------------------------------- build

    def _build_header(self) -> QHBoxLayout:
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(0)
        title = QLabel(strings.STATISTICS_TITLE)
        title.setObjectName("ScreenTitle")
        title_box.addWidget(title)
        subtitle = QLabel(strings.STATS_SUBTITLE)
        subtitle.setObjectName("Muted")
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch(1)

        header.addWidget(QLabel(strings.STATS_FROM))
        self.date_from = QDateEdit(QDate.currentDate().addDays(-30))
        self.date_from.setCalendarPopup(True)
        header.addWidget(self.date_from)
        header.addWidget(QLabel(strings.STATS_TO))
        self.date_to = QDateEdit(QDate.currentDate())
        self.date_to.setCalendarPopup(True)
        header.addWidget(self.date_to)

        self.btn_export_pdf = QPushButton(strings.STATS_EXPORT_PDF)
        self.btn_export_pdf.setObjectName("Secondary")
        self.btn_export_pdf.clicked.connect(self.export_pdf)
        header.addWidget(self.btn_export_pdf)

        self.btn_export_xlsx = QPushButton(strings.STATS_EXPORT_XLSX)
        self.btn_export_xlsx.setObjectName("Secondary")
        self.btn_export_xlsx.clicked.connect(self.export_xlsx)
        header.addWidget(self.btn_export_xlsx)

        refresh = QPushButton(strings.REFRESH)
        refresh.setObjectName("Primary")
        refresh.clicked.connect(self.refresh)
        header.addWidget(refresh)
        return header

    def _section_heading(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("SectionTitle")
        return label

    def _build_kpi_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(SPACING["md"])
        self.kpi_revenue = KpiCard(strings.STATS_REVENUE, "fa5s.coins", *_KPI_BLUE)
        self.kpi_profit = KpiCard(strings.STATS_PROFIT, "fa5s.chart-line", *_KPI_GREEN)
        self.kpi_sales = KpiCard(strings.STATS_SALES_COUNT, "fa5s.receipt", *_KPI_VIOLET)
        self.kpi_discount = KpiCard(strings.STATS_DISCOUNTS, "fa5s.tag", *_KPI_AMBER)
        for card in (
            self.kpi_revenue,
            self.kpi_profit,
            self.kpi_sales,
            self.kpi_discount,
        ):
            row.addWidget(card, stretch=1)
        return row

    def _build_period_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(SPACING["md"])
        self.overview_cards: dict[str, PeriodCard] = {}
        for key in ("today", "this_week", "this_month", "this_year"):
            card = PeriodCard(strings.STATS_OVERVIEW_LABELS[key])
            self.overview_cards[key] = card
            row.addWidget(card, stretch=1)
        return row

    def _build_mid_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(SPACING["md"])

        top_card = SectionCard(strings.STATS_TOP_PRODUCTS, "fa5s.crown")
        self.top_table = DataTable(
            [
                "",
                strings.STATS_COL_PRODUCT,
                strings.STATS_COL_QTY,
                strings.STATS_COL_REVENUE,
            ]
        )
        self.top_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Fixed
        )
        self.top_table.setColumnWidth(0, THUMB_SIZES["table"] + 14)
        self.top_table.verticalHeader().setDefaultSectionSize(THUMB_SIZES["table"] + 10)
        self.top_table.setMinimumHeight(260)
        top_card.body.addWidget(self.top_table)
        row.addWidget(top_card, stretch=3)

        pm_card = SectionCard(strings.STATS_PAYMENT_METHODS, "fa5s.wallet")
        self.pm_share = PaymentShareBar()
        pm_card.body.addWidget(self.pm_share)
        pm_card.body.addStretch(1)
        row.addWidget(pm_card, stretch=2)
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

    # ------------------------------------------------------------- loading

    def _range(self) -> tuple[str, str]:
        return (
            self.date_from.date().toString("yyyy-MM-dd"),
            self.date_to.date().toString("yyyy-MM-dd"),
        )

    def export_pdf(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Enregistrer le rapport", "rapport.pdf", "PDF (*.pdf)"
        )
        if not path:
            return
        df, dt = self._range()
        run_api(
            lambda c: c.get_report_pdf(self.store_id, df, dt),
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
            lambda c: c.get_report_xlsx(self.store_id, df, dt),
            lambda data: self._save_file(path, data),
            lambda err: show_error(self, strings.ERROR_TITLE, err.message),
        )

    def _save_file(self, path: str, data: bytes) -> None:
        try:
            with open(path, "wb") as f:
                f.write(data)
        except OSError as e:
            show_error(self, strings.ERROR_TITLE, f"Erreur d'écriture : {e}")

    def refresh(self) -> None:
        date_from, date_to = self._range()
        self._error_shown = False
        run_api(
            lambda: self.api.list_products(self.store_id),
            self._on_products,
            lambda err: None,  # thumbnails only; tables still render
        )
        run_api(
            lambda: self.api.stats_overview(self.store_id),
            self._on_overview,
            self._on_error,
        )
        run_api(
            lambda: self.api.stats_top_products(self.store_id, date_from, date_to),
            self._on_top,
            self._on_error,
        )
        run_api(
            lambda: self.api.stats_summary(self.store_id, date_from, date_to),
            self._on_summary,
            self._on_error,
        )
        run_api(
            lambda: self.api.stats_payment_methods(self.store_id, date_from, date_to),
            self._on_payment_methods,
            self._on_error,
        )
        self.assoc_stack.show_loading()
        run_api(
            lambda: self.api.stats_associations(self.store_id, date_from, date_to),
            self._on_associations,
            self._on_assoc_error,
        )

    def _on_products(self, products: object) -> None:
        self.products_by_id = {p["id"]: p for p in products}

    def _on_overview(self, overview: object) -> None:
        for period in overview.get("periods", []):
            card = self.overview_cards.get(period["period"])
            if card is not None:
                card.set_period(period)

    def _on_top(self, top: object) -> None:
        top = list(top)
        self.top_table.set_rows(
            [
                ["", t["name"], t["quantity_sold"], fmt.fmt_money(t["revenue"])]
                for t in top
            ]
        )
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

    def _on_summary(self, summary: object) -> None:
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

        self.kpi_sales.set_value(str(count))

        discount_share = (discounts / revenue) if revenue else Decimal("0")
        self.kpi_discount.set_value(
            fmt.fmt_money(discounts),
            sub=f"{fmt.fmt_percent(float(discount_share))} {strings.STATS_OF_REVENUE}",
        )

    def _on_payment_methods(self, methods: object) -> None:
        self.pm_share.set_data(methods)

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
            return  # one dialog per refresh, not one per endpoint
        self._error_shown = True
        if err.code in ("invalid_pin", "pin_not_configured"):
            show_error(self, strings.STATS_PIN_REQUIRED)
        else:
            show_error(self, err.message)
