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
        layout.addWidget(age)

        pay = QPushButton(
            qta.icon("fa5s.hand-holding-usd", color=NEUTRAL["600"]),
            strings.CUSTOMER_RECORD_PAYMENT,
        )
        pay.clicked.connect(lambda: on_pay(credit))
        layout.addWidget(pay)


class AlertsScreen(QWidget):
    def __init__(
        self,
        api,
        store_id: str,
        on_view_product: Callable[[str], None],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.api = api
        self.store_id = store_id
        self.on_view_product = on_view_product
        self.low_stock: list[dict] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(*[SPACING["xl"]] * 4)
        layout.setSpacing(SPACING["md"])

        header = QHBoxLayout()
        title = QLabel(strings.ALERTS_TITLE)
        title.setObjectName("ScreenTitle")
        header.addWidget(title)
        header.addStretch(1)
        refresh = QPushButton(strings.REFRESH)
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

    # ------------------------------------------------------------- loading

    def refresh(self) -> None:
        self.stock_stack.show_loading()
        self.credits_stack.show_loading()
        run_api(
            lambda: self.api.get_alerts(self.store_id),
            self.set_data,
            lambda err: show_error(self, err.message),
        )

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
