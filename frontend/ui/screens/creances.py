"""Créances clients — track and collect outstanding customer balances.

A live list of every sale with money still owed. Each row can be settled
(Encaisser → the shared RecordPaymentDialog) or reprinted (Reçu). The list
can be shown flat (sorted by aging) or grouped by customer with a collapsible
subtotal, and exported as a debt-summary PDF. When nothing is owed, a green
"Aucune créance en cours" empty state is shown.

All network goes through run_api; nothing here blocks the UI thread.
"""

import tempfile
from decimal import Decimal
from pathlib import Path

import qtawesome as qta
import shiboken6
from loguru import logger
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from services import printing
from services.workers import run_api
from ui import format as fmt
from ui import strings
from ui.styles.tokens import NEUTRAL, SEMANTIC, SPACING
from ui.widgets.badge import Badge
from ui.widgets.data_table import DataTable
from ui.widgets.modal import show_error
from ui.widgets.pagination import PaginationBar
from ui.widgets.payment_dialogs import RecordPaymentDialog
from ui.widgets.states import EmptyState, StatefulStack
from ui.widgets.toast import show_toast

_PAGE_SIZE = 50


def _age_kind(days: int) -> str:
    """Aging colour: green < 7 j, orange 7–30 j, red > 30 j."""
    if days < 7:
        return "success"
    if days <= 30:
        return "warning"
    return "danger"


def _as_sale(entry: dict) -> dict:
    """Adapt an OutstandingSale dict to what RecordPaymentDialog expects
    (it keys on ``id`` / ``total_amount`` / ``paid_amount``)."""
    return {
        "id": entry["sale_id"],
        "total_amount": entry["total_amount"],
        "paid_amount": entry["paid_amount"],
    }


class CreancesScreen(QWidget):
    def __init__(self, api, store_id: str, parent=None) -> None:
        super().__init__(parent)
        self.api = api
        self.store_id = store_id
        self.credits: list[dict] = []
        self._grouped = False
        self._page = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(*[SPACING["xl"]] * 4)
        layout.setSpacing(SPACING["md"])

        # ---------------------------------------------------------- header
        header = QHBoxLayout()
        title = QLabel(strings.CREANCES_TITLE)
        title.setObjectName("ScreenTitle")
        header.addWidget(title)
        self.summary_badge = Badge("", "warning")
        header.addWidget(self.summary_badge)
        header.addStretch(1)

        self.search = QLineEdit()
        self.search.setObjectName("SearchInput")
        self.search.setPlaceholderText(strings.CREANCES_SEARCH)
        self.search.setFixedWidth(260)
        self.search.textChanged.connect(lambda _: self._reset_and_render())
        header.addWidget(self.search)

        header.addWidget(self._build_view_toggle())

        self.export_button = QPushButton(
            qta.icon("fa5s.file-pdf", color=NEUTRAL["600"]),
            strings.CREANCES_EXPORT_PDF,
        )
        self.export_button.setObjectName("Secondary")
        self.export_button.clicked.connect(self._export_pdf)
        header.addWidget(self.export_button)

        refresh_button = QPushButton(
            qta.icon("fa5s.sync", color=NEUTRAL["600"]), strings.REFRESH
        )
        refresh_button.setObjectName("Primary")
        refresh_button.clicked.connect(self.refresh)
        header.addWidget(refresh_button)
        layout.addLayout(header)

        # ------------------------------------------------------- flat table
        self.table = DataTable(
            [
                strings.CREANCES_COL_CUSTOMER,
                strings.CREANCES_COL_DATE,
                strings.CREANCES_COL_TOTAL,
                strings.CREANCES_COL_PAID,
                strings.CREANCES_COL_BALANCE,
                strings.CREANCES_COL_AGE,
                strings.CREANCES_COL_ACTIONS,
            ]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.table.horizontalHeader().setSectionResizeMode(
            6, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.verticalHeader().setDefaultSectionSize(44)

        # ------------------------------------------------------ grouped view
        self.grouped_holder = QWidget()
        self.grouped_layout = QVBoxLayout(self.grouped_holder)
        self.grouped_layout.setContentsMargins(0, 0, 0, 0)
        self.grouped_layout.setSpacing(SPACING["sm"])
        grouped_scroll = QScrollArea()
        grouped_scroll.setWidgetResizable(True)
        grouped_scroll.setFrameShape(QFrame.Shape.NoFrame)
        grouped_scroll.setWidget(self.grouped_holder)

        self.view_stack = QStackedWidget()
        self.view_stack.addWidget(self.table)  # index 0 — flat
        self.view_stack.addWidget(grouped_scroll)  # index 1 — grouped

        self.stack = StatefulStack(
            self.view_stack,
            EmptyState(
                "fa5s.check-circle",
                strings.CREANCES_EMPTY,
                strings.CREANCES_EMPTY_HINT,
            ),
        )
        layout.addWidget(self.stack, stretch=1)

        self.pagination = PaginationBar()
        self.pagination.page_changed.connect(self._on_page_changed)
        layout.addWidget(self.pagination)

    def _build_view_toggle(self) -> QWidget:
        group = QWidget()
        group.setObjectName("SegmentGroup")
        group.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        row = QHBoxLayout(group)
        row.setContentsMargins(3, 3, 3, 3)
        row.setSpacing(3)
        button_group = QButtonGroup(group)
        button_group.setExclusive(True)
        for key, label in (
            (False, strings.CREANCES_VIEW_FLAT),
            (True, strings.CREANCES_VIEW_GROUPED),
        ):
            button = QPushButton(label)
            button.setObjectName("SegmentPill")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _=False, k=key: self._set_grouped(k))
            button.setChecked(key == self._grouped)
            button_group.addButton(button)
            row.addWidget(button)
        return group

    # ------------------------------------------------------------- loading

    def refresh(self) -> None:
        self.stack.show_loading()
        run_api(
            lambda: self.api.list_outstanding_sales(self.store_id),
            self._on_loaded,
            self._on_error,
        )

    def _on_loaded(self, credits: object) -> None:
        if not shiboken6.isValid(self):
            return
        self.credits = list(credits or [])
        self._render()

    def _on_error(self, err) -> None:
        if not shiboken6.isValid(self):
            return
        self.stack.show_empty()
        if err.code in ("invalid_pin", "pin_not_configured"):
            show_error(self, strings.PIN_REQUIRED_ACTION)
        else:
            show_error(self, err.message)

    def _set_grouped(self, grouped: bool) -> None:
        self._grouped = grouped
        self._page = 0
        self._render()

    def _reset_and_render(self) -> None:
        self._page = 0
        self._render()

    def _on_page_changed(self, page: int) -> None:
        self._page = page
        self._render()

    # ------------------------------------------------------------- render

    def _visible(self) -> list[dict]:
        query = self.search.text().strip().casefold()
        rows = self.credits
        if query:
            rows = [
                c
                for c in rows
                if query in (c.get("customer_name") or "").casefold()
                or query in (c.get("customer_phone") or "").casefold()
            ]
        return rows

    def _update_summary(self) -> None:
        total = sum((Decimal(str(c["balance"])) for c in self.credits), Decimal("0"))
        self.summary_badge.setText(
            strings.CREANCES_SUMMARY.format(
                total=fmt.fmt_money(total), count=len(self.credits)
            )
        )

    def _render(self) -> None:
        self._update_summary()
        rows = self._visible()
        if not rows:
            self.stack.show_empty()
            self.pagination.set_state(0, 1)
            return
        self.view_stack.setCurrentIndex(1 if self._grouped else 0)
        if self._grouped:
            self._render_grouped(rows)
            self.pagination.set_state(0, 1)
        else:
            total_pages = (len(rows) + _PAGE_SIZE - 1) // _PAGE_SIZE
            self._page = min(self._page, total_pages - 1)
            start = self._page * _PAGE_SIZE
            self._render_flat(rows[start : start + _PAGE_SIZE])
            self.pagination.set_state(self._page, total_pages)
        self.stack.show_content()

    def _render_flat(self, rows: list[dict]) -> None:
        rows = sorted(rows, key=lambda c: c.get("age_days", 0), reverse=True)
        self.table.set_rows(
            [
                [
                    self._customer_text(c),
                    fmt.fmt_date(c.get("created_at")),
                    fmt.fmt_money(c["total_amount"]),
                    fmt.fmt_money(c["paid_amount"]),
                    "",  # balance widget
                    "",  # aging badge
                    "",  # actions
                ]
                for c in rows
            ]
        )
        for row, credit in enumerate(rows):
            self.table.setCellWidget(row, 4, self._balance_cell(credit))
            self.table.setCellWidget(row, 5, self._aging_cell(credit))
            self.table.setCellWidget(row, 6, self._actions_cell(credit))

    def _render_grouped(self, rows: list[dict]) -> None:
        while self.grouped_layout.count():
            item = self.grouped_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        groups: dict[str, list[dict]] = {}
        for credit in rows:
            key = credit.get("customer_name") or strings.CUSTOMER_ANONYMOUS
            groups.setdefault(key, []).append(credit)
        for name in sorted(groups):
            self.grouped_layout.addWidget(self._group_widget(name, groups[name]))
        self.grouped_layout.addStretch(1)

    # ----------------------------------------------------------- cell parts

    @staticmethod
    def _customer_text(credit: dict) -> str:
        name = credit.get("customer_name") or strings.CUSTOMER_ANONYMOUS
        phone = credit.get("customer_phone")
        return f"{name}\n{phone}" if phone else name

    @staticmethod
    def _balance_cell(credit: dict) -> QWidget:
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(SPACING["xs"], 2, SPACING["xs"], 2)
        label = QLabel(fmt.fmt_money(credit["balance"]))
        label.setStyleSheet(
            f"color: {SEMANTIC['danger']}; font-weight: 700; background: transparent;"
        )
        row.addWidget(label)
        row.addStretch(1)
        return holder

    @staticmethod
    def _aging_cell(credit: dict) -> QWidget:
        days = int(credit.get("age_days", 0))
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(SPACING["xs"], 2, SPACING["xs"], 2)
        row.addWidget(
            Badge(strings.CREANCES_AGE_DAYS.format(days=days), _age_kind(days))
        )
        row.addStretch(1)
        return holder

    def _actions_cell(self, credit: dict) -> QWidget:
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(SPACING["xs"], 2, SPACING["xs"], 2)
        row.setSpacing(SPACING["xs"])
        encaisser = QPushButton(
            qta.icon("fa5s.hand-holding-usd", color="white"),
            strings.CREANCES_ENCAISSER,
        )
        encaisser.setObjectName("Primary")
        encaisser.clicked.connect(lambda _=False, c=credit: self._encaisser(c))
        row.addWidget(encaisser)
        receipt = QPushButton(
            qta.icon("fa5s.print", color=NEUTRAL["600"]), strings.CREANCES_RECEIPT
        )
        receipt.setObjectName("Ghost")
        receipt.clicked.connect(lambda _=False, c=credit: self._print_receipt(c))
        row.addWidget(receipt)
        row.addStretch(1)
        return holder

    def _group_widget(self, name: str, credits: list[dict]) -> QWidget:
        subtotal = sum((Decimal(str(c["balance"])) for c in credits), Decimal("0"))
        container = QFrame()
        container.setObjectName("Card")
        container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        outer = QVBoxLayout(container)
        outer.setContentsMargins(
            SPACING["md"], SPACING["sm"], SPACING["md"], SPACING["sm"]
        )
        outer.setSpacing(SPACING["xs"])

        subtotal_text = strings.CREANCES_GROUP_SUBTOTAL.format(
            total=fmt.fmt_money(subtotal)
        )
        toggle = QPushButton(f"▾  {name}  ·  {subtotal_text}")
        toggle.setObjectName("Ghost")
        toggle.setCheckable(True)
        toggle.setChecked(True)
        toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        toggle.setStyleSheet("font-weight: 700;")
        outer.addWidget(toggle)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(SPACING["xs"])
        for credit in sorted(credits, key=lambda c: c.get("age_days", 0), reverse=True):
            body_layout.addWidget(self._group_row(credit))
        outer.addWidget(body)

        def _toggle(checked: bool) -> None:
            body.setVisible(checked)
            toggle.setText(("▾" if checked else "▸") + f"  {name}  ·  " + subtotal_text)

        toggle.toggled.connect(_toggle)
        return container

    def _group_row(self, credit: dict) -> QWidget:
        row_widget = QFrame()
        row_widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        row = QHBoxLayout(row_widget)
        row.setContentsMargins(SPACING["sm"], 2, SPACING["sm"], 2)
        row.setSpacing(SPACING["md"])
        date = QLabel(fmt.fmt_date(credit.get("created_at")))
        date.setObjectName("Muted")
        row.addWidget(date)
        balance = QLabel(fmt.fmt_money(credit["balance"]))
        balance.setStyleSheet(
            f"color: {SEMANTIC['danger']}; font-weight: 700; background: transparent;"
        )
        row.addWidget(balance)
        days = int(credit.get("age_days", 0))
        row.addWidget(
            Badge(strings.CREANCES_AGE_DAYS.format(days=days), _age_kind(days))
        )
        row.addStretch(1)
        row.addWidget(self._actions_cell(credit))
        return row_widget

    # ------------------------------------------------------------- actions

    def _encaisser(self, credit: dict) -> None:
        dialog = RecordPaymentDialog(self.api, _as_sale(credit), parent=self)
        if dialog.exec() and dialog.result_sale:
            show_toast(self, strings.CREANCES_PAYMENT_DONE)
            window = self.window()
            if hasattr(window, "refresh_alerts_badge"):
                window.refresh_alerts_badge()
            self.refresh()

    def _print_receipt(self, credit: dict) -> None:
        run_api(
            lambda: self.api.get_receipt_pdf(credit["sale_id"]),
            self._on_receipt,
            lambda err: show_error(self, err.message),
        )

    def _on_receipt(self, pdf: object) -> None:
        path = Path(tempfile.gettempdir()) / "recu_creance.pdf"
        try:
            path.write_bytes(pdf)
            printing.print_pdf(path, printing.get_selected_printer())
        except OSError as exc:
            logger.warning("Receipt print failed: {}", exc)
            show_error(self, strings.RECEIPT_PRINT_FAILED.format(path=path))

    def _export_pdf(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, strings.CREANCES_EXPORT_PDF, "creances.pdf", "PDF (*.pdf)"
        )
        if not path:
            return
        run_api(
            lambda: self.api.get_outstanding_report_pdf(self.store_id),
            lambda data: self._save_pdf(path, data),
            lambda err: show_error(self, err.message),
        )

    def _save_pdf(self, path: str, data: bytes) -> None:
        try:
            Path(path).write_bytes(data)
            show_toast(self, strings.EXPORT_SAVED_TOAST.format(path=path))
        except OSError as exc:
            show_error(self, str(exc))
