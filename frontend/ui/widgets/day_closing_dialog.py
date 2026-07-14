"""Daily cash-register closing dialog (clôture de caisse).

Three sections:
  A — automatic recap (sales count, revenue, payment split, discounts,
      refunds) fetched from the server before the dialog opens;
  B — physical count: the cash counted in the drawer, with a live gap vs the
      theoretical cash, plus a discrepancy note;
  C — actions: print the closing report PDF, or confirm (persist) the closing.

Opening the dialog is gated behind PIN entry by the caller; the verified PIN
is forwarded here and used to persist the closing.
"""

import tempfile
from decimal import Decimal
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
)

from services import printing
from services.workers import run_api
from ui import format as fmt
from ui import strings
from ui.styles.tokens import SEMANTIC
from ui.widgets.modal import ModalDialog, show_error


class DayClosingDialog(ModalDialog):
    """Persists the closing on ``self.result`` when confirmed."""

    def __init__(
        self, api, store_id: str, day: str, summary: dict, pin: str, parent=None
    ) -> None:
        super().__init__(strings.CLOSING_TITLE, parent)
        self.api = api
        self.store_id = store_id
        self.day = day
        self.summary = summary
        self.pin = pin
        self.result: dict | None = None
        self.expected = Decimal(str(summary.get("expected_cash", "0")))
        self.setMinimumWidth(480)

        # ------------------------------------------- A — automatic recap
        self._section_title(strings.CLOSING_SECTION_SUMMARY)
        self._row(strings.CLOSING_SALES_COUNT, str(summary.get("sales_count", 0)))
        self._row(
            strings.CLOSING_REVENUE, fmt.fmt_money(summary.get("total_revenue", 0))
        )
        self._row(strings.CLOSING_CASH, fmt.fmt_money(summary.get("cash_total", 0)))
        if Decimal(str(summary.get("card_total", 0))) > 0:
            self._row(strings.CLOSING_CARD, fmt.fmt_money(summary.get("card_total", 0)))
        if Decimal(str(summary.get("transfer_total", 0))) > 0:
            self._row(
                strings.CLOSING_TRANSFER,
                fmt.fmt_money(summary.get("transfer_total", 0)),
            )
        self._row(
            strings.CLOSING_DISCOUNTS,
            fmt.fmt_money(summary.get("total_discounts", 0)),
        )
        self._row(
            strings.CLOSING_REFUNDS, fmt.fmt_money(summary.get("total_refunds", 0))
        )
        self._divider()
        self._row(
            strings.CLOSING_EXPECTED_CASH,
            fmt.fmt_money(self.expected),
            bold=True,
        )

        # ------------------------------------------- B — physical count
        self._section_title(strings.CLOSING_SECTION_COUNT)
        count_label = QLabel(strings.CLOSING_PHYSICAL_LABEL)
        count_label.setObjectName("Caption")
        self.content.addWidget(count_label)
        self.physical_input = QDoubleSpinBox()
        self.physical_input.setDecimals(2)
        self.physical_input.setMaximum(99_999_999.99)
        self.physical_input.setAlignment(Qt.AlignmentFlag.AlignTrailing)
        self.physical_input.valueChanged.connect(self._update_gap)
        self.content.addWidget(self.physical_input)

        self.gap_label = QLabel("")
        self.content.addWidget(self.gap_label)

        note_label = QLabel(strings.CLOSING_NOTE_LABEL)
        note_label.setObjectName("Caption")
        self.content.addWidget(note_label)
        self.note_input = QLineEdit()
        self.note_input.setPlaceholderText(strings.CLOSING_NOTE_PLACEHOLDER)
        self.content.addWidget(self.note_input)

        # ------------------------------------------- C — actions
        self.print_button = QPushButton(strings.CLOSING_PRINT)
        self.print_button.setObjectName("Secondary")
        self.print_button.clicked.connect(self._print_report)
        self.buttons.addButton(self.print_button, self.buttons.ButtonRole.ActionRole)

        self.ok_button.setText(strings.CLOSING_CONFIRM)
        self.ok_button.setObjectName("Primary")
        self._update_gap()

    # ------------------------------------------------------------- layout

    def _section_title(self, text: str) -> None:
        label = QLabel(text)
        label.setObjectName("SectionTitle")
        self.content.addWidget(label)

    def _divider(self) -> None:
        divider = QFrame()
        divider.setObjectName("HDivider")
        divider.setFixedHeight(1)
        self.content.addWidget(divider)

    def _row(self, caption: str, value: str, bold: bool = False) -> None:
        row = QFrame()
        row.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        caption_label = QLabel(caption)
        caption_label.setObjectName("Secondary")
        layout.addWidget(caption_label)
        layout.addStretch(1)
        value_label = QLabel(value)
        weight = "700" if bold else "600"
        value_label.setStyleSheet(f"font-weight: {weight}; background: transparent;")
        layout.addWidget(value_label)
        self.content.addWidget(row)

    # ------------------------------------------------------------- gap

    def _update_gap(self) -> None:
        physical = Decimal(f"{self.physical_input.value():.2f}")
        gap = physical - self.expected
        if gap > 0:
            text = strings.CLOSING_GAP_POS.format(amount=fmt.fmt_money(gap))
            color = SEMANTIC["success"]
        elif gap < 0:
            text = strings.CLOSING_GAP_NEG.format(amount=fmt.fmt_money(abs(gap)))
            color = SEMANTIC["danger"]
        else:
            text = fmt.fmt_money(gap)
            color = SEMANTIC["success"]
        self.gap_label.setText(f"{strings.CLOSING_GAP_LABEL} {text}")
        self.gap_label.setStyleSheet(
            f"color: {color}; font-weight: 700; background: transparent;"
        )

    # ------------------------------------------------------------- actions

    def _print_report(self) -> None:
        physical = f"{self.physical_input.value():.2f}"
        notes = self.note_input.text().strip() or None
        run_api(
            lambda: self.api.get_closing_pdf(self.store_id, self.day, physical, notes),
            self._on_pdf,
            lambda err: show_error(self, err.message),
        )

    def _on_pdf(self, pdf: object) -> None:
        path = Path(tempfile.gettempdir()) / f"cloture_{self.day}.pdf"
        try:
            path.write_bytes(pdf)
            printing.open_file(path)
        except OSError as exc:
            show_error(self, strings.OPEN_PDF_FAILED.format(path=exc))

    def accept(self) -> None:
        physical = f"{self.physical_input.value():.2f}"
        notes = self.note_input.text().strip() or None
        self.ok_button.setEnabled(False)
        run_api(
            lambda: self.api.close_day(
                self.store_id, self.day, physical, notes, self.pin
            ),
            self._on_done,
            self._on_error,
        )

    def _on_done(self, result: object) -> None:
        self.result = result
        super().accept()

    def _on_error(self, err) -> None:
        self.ok_button.setEnabled(True)
        show_error(self, err.message)
