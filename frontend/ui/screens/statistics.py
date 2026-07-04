"""Statistiques — overview with previous-period comparison, top products,
and market-basket association rules ("souvent achetés ensemble").

All statistics endpoints are owner data (they derive from cost_price): the
API requires the PIN, which the client sends automatically when it was
captured at login.
"""

from decimal import Decimal

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QDateEdit,
    QGridLayout,
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
from ui.styles.tokens import SPACING, THUMB_SIZES
from ui.widgets.badge import DeltaChip
from ui.widgets.card import Card, SectionCard
from ui.widgets.data_table import DataTable
from ui.widgets.modal import show_error
from ui.widgets.states import EmptyState, StatefulStack
from ui.widgets.thumb import Thumb


class OverviewCard(Card):
    """One calendar period: revenue / profit / sales, each with its delta."""

    def __init__(self, title: str, parent=None) -> None:
        super().__init__(parent)
        caption = QLabel(title.upper())
        caption.setObjectName("StatCardTitle")
        self.body.addWidget(caption)

        self.revenue_value = QLabel("—")
        self.revenue_value.setObjectName("StatCardValue")
        self.body.addWidget(self.revenue_value)

        grid = QGridLayout()
        grid.setSpacing(SPACING["xs"])
        self._chips: dict[str, DeltaChip] = {}
        self._values: dict[str, QLabel] = {}
        for row, (key, label) in enumerate(
            [
                ("revenue", strings.STATS_REVENUE),
                ("gross_profit", strings.STATS_PROFIT),
                ("sales_count", strings.STATS_SALES_COUNT),
            ]
        ):
            name = QLabel(label)
            name.setObjectName("Muted")
            grid.addWidget(name, row, 0)
            value = QLabel("—")
            value.setStyleSheet("font-weight: 600;")
            value.setAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            grid.addWidget(value, row, 1)
            chip = DeltaChip()
            chip.setToolTip(strings.STATS_VS_PREVIOUS)
            grid.addWidget(chip, row, 2)
            self._values[key] = value
            self._chips[key] = chip
        self.body.addLayout(grid)
        self.body.addStretch(1)

    def set_period(self, period: dict) -> None:
        current, previous = period["current"], period["previous"]
        self.revenue_value.setText(fmt.fmt_money(current["revenue"]))
        for key in ("revenue", "gross_profit", "sales_count"):
            now = Decimal(str(current[key]))
            before = Decimal(str(previous[key]))
            if key == "sales_count":
                self._values[key].setText(str(current[key]))
            else:
                self._values[key].setText(fmt.fmt_money(current[key]))
            self._chips[key].set_delta(now, before)


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

        header = QHBoxLayout()
        title = QLabel(strings.STATISTICS_TITLE)
        title.setObjectName("ScreenTitle")
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(QLabel(strings.STATS_FROM))
        self.date_from = QDateEdit(QDate.currentDate().addDays(-30))
        self.date_from.setCalendarPopup(True)
        header.addWidget(self.date_from)
        header.addWidget(QLabel(strings.STATS_TO))
        self.date_to = QDateEdit(QDate.currentDate())
        self.date_to.setCalendarPopup(True)
        header.addWidget(self.date_to)
        refresh = QPushButton(strings.REFRESH)
        refresh.setObjectName("Primary")
        refresh.clicked.connect(self.refresh)
        header.addWidget(refresh)
        outer.addLayout(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, SPACING["sm"], 0)
        layout.setSpacing(SPACING["md"])

        # Overview cards — fixed calendar periods with previous comparison.
        cards_row = QHBoxLayout()
        cards_row.setSpacing(SPACING["sm"])
        self.overview_cards: dict[str, OverviewCard] = {}
        for key in ("today", "this_week", "this_month", "this_year"):
            card = OverviewCard(strings.STATS_OVERVIEW_LABELS[key])
            self.overview_cards[key] = card
            cards_row.addWidget(card, stretch=1)
        layout.addLayout(cards_row)

        # Top products (range-driven) with thumbnails.
        top_card = SectionCard(strings.STATS_TOP_PRODUCTS, "fa5s.crown")
        self.top_table = DataTable(
            [
                "",
                strings.STATS_COL_PRODUCT,
                strings.STATS_COL_QTY,
                strings.STATS_COL_REVENUE,
            ]
        )
        from PySide6.QtWidgets import QHeaderView

        self.top_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Fixed
        )
        self.top_table.setColumnWidth(0, THUMB_SIZES["table"] + 14)
        self.top_table.verticalHeader().setDefaultSectionSize(THUMB_SIZES["table"] + 10)
        self.top_table.setMinimumHeight(240)
        top_card.body.addWidget(self.top_table)
        layout.addWidget(top_card)

        # Associations (range-driven).
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
        self.assoc_stack.setMinimumHeight(180)
        assoc_card.body.addWidget(self.assoc_stack)
        layout.addWidget(assoc_card)
        layout.addStretch(1)

        scroll.setWidget(content)
        outer.addWidget(scroll, stretch=1)

    # ------------------------------------------------------------- loading

    def _range(self) -> tuple[str, str]:
        return (
            self.date_from.date().toString("yyyy-MM-dd"),
            self.date_to.date().toString("yyyy-MM-dd"),
        )

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
