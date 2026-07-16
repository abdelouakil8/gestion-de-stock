"""Alertes — low-stock products and outstanding credit sales.

Fed by the single GET /alerts endpoint (also polled by the shell for the
sidebar badge). Credits are listed oldest debt first with the age visually
escalated (neutral → warning → danger); each row carries an inline
"Encaisser un paiement" action that refreshes both the list and the badge.
"""

from collections.abc import Callable

import qtawesome as qta
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
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
from ui.styles.tokens import NEUTRAL, SPACING, THUMB_SIZES
from ui.widgets.badge import Badge
from ui.widgets.card import SectionCard
from ui.widgets.data_table import DataTable
from ui.widgets.modal import show_error
from ui.widgets.payment_dialogs import RecordPaymentDialog
from ui.widgets.states import EmptyState, StatefulStack
from ui.widgets.thumb import Thumb
from ui.widgets.toast import show_toast

# Debt age escalation thresholds (days).
_AGE_WARNING = 7
_AGE_DANGER = 30


def _age_kind(days: int) -> str:
    if days >= _AGE_DANGER:
        return "danger"
    if days >= _AGE_WARNING:
        return "warning"
    return "neutral"


class _CreditRow(QWidget):
    """One outstanding sale: customer, amounts, age chip, pay action."""

    def __init__(self, credit: dict, on_pay: Callable[[dict], None]) -> None:
        super().__init__()
        self.setObjectName("RuleCard")
        # QWidget subclass: required for the QSS card background/border.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(
            SPACING["md"], SPACING["sm"], SPACING["md"], SPACING["sm"]
        )
        layout.setSpacing(SPACING["md"])

        who = QVBoxLayout()
        who.setSpacing(2)
        name = QLabel(credit.get("customer_name") or "—")
        name.setStyleSheet("font-weight: 700; background: transparent;")
        who.addWidget(name)
        phone = QLabel(credit.get("customer_phone") or "")
        phone.setObjectName("Muted")
        who.addWidget(phone)
        layout.addLayout(who, stretch=1)

        amounts = QVBoxLayout()
        amounts.setSpacing(2)
        totals = QLabel(
            strings.ALERTS_CREDIT_LINE.format(
                total=fmt.fmt_money(credit["total_amount"]),
                paid=fmt.fmt_money(credit["paid_amount"]),
            )
        )
        totals.setObjectName("Secondary")
        amounts.addWidget(totals)
        remaining = QLabel(
            strings.ALERTS_REMAINING.format(balance=fmt.fmt_money(credit["balance"]))
        )
        remaining.setStyleSheet("font-weight: 700; background: transparent;")
        amounts.addWidget(remaining)
        layout.addLayout(amounts)

        age = Badge(
            strings.ALERTS_AGE_DAYS.format(days=credit["age_days"]),
            _age_kind(credit["age_days"]),
        )
        # The color code (grey/orange/red) is explained on hover.
        age.setToolTip(strings.ALERTS_AGE_TOOLTIP)
        layout.addWidget(age)

        pay = QPushButton(
            qta.icon("fa5s.hand-holding-usd", color=NEUTRAL["600"]),
            strings.CUSTOMER_RECORD_PAYMENT,
        )
        pay.setObjectName("Ghost")
        pay.clicked.connect(lambda: on_pay(credit))
        layout.addWidget(pay)


class _DeadStockRow(QFrame):
    """One dormant product: thumbnail, name/category, stock, age, action."""

    def __init__(self, item: dict, on_create_purchase: Callable[[dict], None]) -> None:
        super().__init__()
        self.setObjectName("RuleCard")
        # QWidget subclass: required for the QSS card background/border.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(
            SPACING["md"], SPACING["sm"], SPACING["md"], SPACING["sm"]
        )
        layout.setSpacing(SPACING["md"])

        thumb = Thumb(THUMB_SIZES["list"])
        thumb.set_product(
            {
                "id": item["product_id"],
                "name": item["name"],
                "image_path": item.get("image_path"),
            }
        )
        layout.addWidget(thumb)

        who = QVBoxLayout()
        who.setSpacing(2)
        name = QLabel(item["name"])
        name.setStyleSheet("font-weight: 700; background: transparent;")
        who.addWidget(name)
        category = QLabel(item.get("category_name") or strings.ALERTS_NO_CATEGORY)
        category.setObjectName("Muted")
        who.addWidget(category)
        layout.addLayout(who, stretch=1)

        stock = QLabel(
            strings.ALERTS_DEAD_STOCK_IN_STOCK.format(qty=item["stock_quantity"])
        )
        stock.setObjectName("Secondary")
        layout.addWidget(stock)

        days = item.get("days_since")
        # Amber below 90 days, red at/after 90 (and for never-sold products).
        overdue = days is None or days >= 90
        if days is None:
            age_text = strings.ALERTS_DEAD_STOCK_NEVER
        else:
            age_text = strings.ALERTS_DEAD_STOCK_NOT_SOLD.format(days=days)
        age = Badge(age_text, "danger" if overdue else "warning")
        layout.addWidget(age)

        create = QPushButton(
            qta.icon("fa5s.dolly", color=NEUTRAL["600"]),
            strings.ALERTS_DEAD_STOCK_CREATE_PO,
        )
        create.setObjectName("Secondary")
        create.clicked.connect(
            lambda: on_create_purchase({"id": item["product_id"], "name": item["name"]})
        )
        layout.addWidget(create)


class AlertsScreen(QWidget):
    def __init__(
        self,
        api,
        store_id: str,
        on_view_product: Callable[[str], None],
        on_create_purchase: Callable[[dict], None],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.api = api
        self.store_id = store_id
        self.on_view_product = on_view_product
        self.on_create_purchase = on_create_purchase
        self.low_stock: list[dict] = []
        self._dead_stock_days = 60

        layout = QVBoxLayout(self)
        layout.setContentsMargins(*[SPACING["xl"]] * 4)
        layout.setSpacing(SPACING["md"])

        header = QHBoxLayout()
        title = QLabel(strings.ALERTS_TITLE)
        title.setObjectName("ScreenTitle")
        header.addWidget(title)
        header.addStretch(1)
        refresh = QPushButton(strings.REFRESH)
        refresh.setObjectName("Ghost")
        refresh.clicked.connect(self.refresh)
        header.addWidget(refresh)
        layout.addLayout(header)

        # ---------------------------------------------------- low stock
        stock_card = SectionCard(strings.ALERTS_LOW_STOCK, "fa5s.exclamation-triangle")
        self.stock_count_badge = Badge("0", "neutral")
        stock_card.header.addWidget(self.stock_count_badge)
        self.stock_table = DataTable(
            [
                "",
                strings.ALERTS_COL_PRODUCT,
                strings.ALERTS_COL_STOCK,
                strings.ALERTS_COL_THRESHOLD,
                "",
            ]
        )
        from PySide6.QtWidgets import QHeaderView

        self.stock_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Fixed
        )
        self.stock_table.setColumnWidth(0, THUMB_SIZES["table"] + 14)
        self.stock_table.verticalHeader().setDefaultSectionSize(
            THUMB_SIZES["table"] + 10
        )
        self.stock_stack = StatefulStack(
            self.stock_table,
            EmptyState(
                "fa5s.check-circle",
                strings.ALERTS_LOW_STOCK_EMPTY,
                strings.ALERTS_LOW_STOCK_EMPTY_HINT,
            ),
        )
        stock_card.body.addWidget(self.stock_stack)
        layout.addWidget(stock_card, stretch=1)

        # ------------------------------------------------------ credits
        credit_card = SectionCard(strings.ALERTS_CREDITS, "fa5s.hand-holding-usd")
        self.credit_count_badge = Badge("0", "neutral")
        credit_card.header.addWidget(self.credit_count_badge)

        self.credits_holder = QWidget()
        self.credits_layout = QVBoxLayout(self.credits_holder)
        self.credits_layout.setContentsMargins(0, 0, 0, 0)
        self.credits_layout.setSpacing(SPACING["sm"])
        credits_scroll = QScrollArea()
        credits_scroll.setWidgetResizable(True)
        credits_scroll.setWidget(self.credits_holder)
        self.credits_stack = StatefulStack(
            credits_scroll,
            EmptyState(
                "fa5s.check-circle",
                strings.ALERTS_CREDITS_EMPTY,
                strings.ALERTS_CREDITS_EMPTY_HINT,
            ),
        )
        credit_card.body.addWidget(self.credits_stack)
        layout.addWidget(credit_card, stretch=1)

        # -------------------------------------------------- dead stock
        dead_card = SectionCard(strings.STATS_DEAD_STOCK_TITLE, "fa5s.hourglass-half")
        self.dead_count_badge = Badge("0", "neutral")
        dead_card.header.addWidget(self.dead_count_badge)
        dead_card.header.addWidget(self._build_period_toggle())

        self.dead_holder = QWidget()
        self.dead_layout = QVBoxLayout(self.dead_holder)
        self.dead_layout.setContentsMargins(0, 0, 0, 0)
        self.dead_layout.setSpacing(SPACING["sm"])
        dead_scroll = QScrollArea()
        dead_scroll.setWidgetResizable(True)
        dead_scroll.setWidget(self.dead_holder)
        self.dead_empty = EmptyState(
            "fa5s.check-circle",
            strings.ALERTS_DEAD_STOCK_EMPTY.format(period=self._dead_stock_days),
            strings.ALERTS_DEAD_STOCK_EMPTY_HINT,
        )
        self.dead_stack = StatefulStack(dead_scroll, self.dead_empty)
        dead_card.body.addWidget(self.dead_stack)
        layout.addWidget(dead_card, stretch=1)

    def _build_period_toggle(self) -> QWidget:
        """Segmented 30/60/90-day selector for the dead-stock window."""
        holder = QWidget()
        holder.setObjectName("SegmentGroup")
        holder.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        row = QHBoxLayout(holder)
        row.setContentsMargins(3, 3, 3, 3)
        row.setSpacing(3)
        self._period_group = QButtonGroup(self)
        self._period_group.setExclusive(True)
        for days, label in (
            (30, strings.STATS_DEAD_30),
            (60, strings.STATS_DEAD_60),
            (90, strings.STATS_DEAD_90),
        ):
            button = QPushButton(label)
            button.setObjectName("SegmentPill")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setChecked(days == self._dead_stock_days)
            button.clicked.connect(lambda _=None, d=days: self._on_period_changed(d))
            self._period_group.addButton(button)
            row.addWidget(button)
        return holder

    def _on_period_changed(self, days: int) -> None:
        self._dead_stock_days = days
        self.dead_empty.set_message(strings.ALERTS_DEAD_STOCK_EMPTY.format(period=days))
        self.reload_dead_stock(days)

    # ------------------------------------------------------------- loading

    def refresh(self) -> None:
        self.stock_stack.show_loading()
        self.credits_stack.show_loading()
        run_api(
            lambda: self.api.get_alerts(self.store_id),
            self.set_data,
            lambda err: show_error(self, err.message),
        )
        self.reload_dead_stock(self._dead_stock_days)

    def reload_dead_stock(self, days: int) -> None:
        self.dead_stack.show_loading()
        run_api(
            lambda: self.api.stats_dead_stock(self.store_id, days=days, limit=20),
            self._on_dead_stock,
            self._on_dead_stock_error,
        )

    def _on_dead_stock(self, items: object) -> None:
        items = list(items or [])
        self.dead_count_badge.setText(str(len(items)))
        while self.dead_layout.count():
            row = self.dead_layout.takeAt(0)
            if row.widget() is not None:
                row.widget().deleteLater()
        for item in items:
            self.dead_layout.addWidget(_DeadStockRow(item, self.on_create_purchase))
        self.dead_layout.addStretch(1)
        if items:
            self.dead_stack.show_content()
        else:
            self.dead_stack.show_empty()

    def _on_dead_stock_error(self, err) -> None:
        # Dead stock is owner-gated (profit data); a PIN failure just leaves
        # the section empty rather than interrupting the alerts screen.
        self.dead_count_badge.setText("0")
        self.dead_stack.show_empty()

    def set_data(self, alerts: object) -> None:
        """Render alerts (also called by the shell's badge poll)."""
        summary = alerts.get("summary", {})
        self.stock_count_badge.setText(str(summary.get("low_stock_count", 0)))
        self.stock_count_badge.set_kind(
            "danger" if summary.get("low_stock_count") else "neutral"
        )
        self.credit_count_badge.setText(
            str(summary.get("outstanding_credits_count", 0))
        )
        self.credit_count_badge.set_kind(
            "warning" if summary.get("outstanding_credits_count") else "neutral"
        )

        # Low stock table.
        self.low_stock = list(alerts.get("low_stock", []))
        self.stock_table.set_rows(
            [
                ["", p["name"], "", str(p["low_stock_threshold"]), ""]
                for p in self.low_stock
            ]
        )
        for row, product in enumerate(self.low_stock):
            thumb = Thumb(THUMB_SIZES["table"])
            thumb.set_letter(product["name"])
            thumb_holder = QWidget()
            thumb_layout = QHBoxLayout(thumb_holder)
            thumb_layout.setContentsMargins(4, 2, 4, 2)
            thumb_layout.addWidget(thumb, alignment=Qt.AlignmentFlag.AlignCenter)
            self.stock_table.setCellWidget(row, 0, thumb_holder)

            stock_holder = QWidget()
            stock_layout = QHBoxLayout(stock_holder)
            stock_layout.setContentsMargins(4, 2, 4, 2)
            kind = "danger" if product["stock_quantity"] <= 0 else "warning"
            stock_layout.addWidget(Badge(str(product["stock_quantity"]), kind))
            stock_layout.addStretch(1)
            self.stock_table.setCellWidget(row, 2, stock_holder)

            view = QPushButton(strings.ALERTS_VIEW_PRODUCT)
            view.setObjectName("Ghost")
            view.clicked.connect(
                lambda _, pid=product["product_id"]: self.on_view_product(pid)
            )
            self.stock_table.setCellWidget(row, 4, view)
        if self.low_stock:
            self.stock_stack.show_content()
        else:
            self.stock_stack.show_empty()

        # Credits, oldest first (already sorted by the API).
        while self.credits_layout.count():
            item = self.credits_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        credits = list(alerts.get("outstanding_credits", []))
        for credit in credits:
            self.credits_layout.addWidget(_CreditRow(credit, self._pay_credit))
        self.credits_layout.addStretch(1)
        if credits:
            self.credits_stack.show_content()
        else:
            self.credits_stack.show_empty()

    # ------------------------------------------------------------- actions

    def _pay_credit(self, credit: dict) -> None:
        sale = {
            "id": str(credit["sale_id"]),
            "total_amount": credit["total_amount"],
            "paid_amount": credit["paid_amount"],
        }
        dialog = RecordPaymentDialog(self.api, sale, parent=self)
        if dialog.exec() and dialog.result_sale is not None:
            paid_now = dialog.amount_input.decimal()
            show_toast(
                self,
                strings.PAYMENT_RECORD_DONE.format(amount=fmt.fmt_money(paid_now)),
            )
            self.refresh()
            window = self.window()
            if hasattr(window, "refresh_alerts_badge"):
                window.refresh_alerts_badge()
