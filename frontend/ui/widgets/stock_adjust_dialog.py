"""Manual stock-adjustment dialog — a guided 3-step flow.

  1. pick the product (embeds ProductSearchBox) and see its current stock;
  2. enter the counted real stock, with a live +N / -N delta, a reason and an
     optional note;
  3. confirm with a summary sentence + the owner PIN (server-verified).

The whole write is one atomic server call (POST /products/{id}/adjust-stock);
the freshly typed PIN is sent so the confirmation cannot be bypassed.
"""

from PySide6.QtWidgets import (
    QComboBox,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from services.workers import run_api
from ui import strings
from ui.styles.tokens import SEMANTIC, SPACING
from ui.widgets.modal import ModalDialog, show_error
from ui.widgets.product_search import ProductSearchBox


class StockAdjustDialog(ModalDialog):
    """Returns the server response on ``self.result`` when accepted."""

    def __init__(self, api, store_id: str, parent=None) -> None:
        super().__init__(strings.ADJUST_TITLE, parent)
        self.api = api
        self.store_id = store_id
        self.product: dict | None = None
        self.result: dict | None = None
        self._step = 0
        self.setMinimumWidth(520)

        self.step_label = QLabel("")
        self.step_label.setObjectName("Caption")
        self.content.addWidget(self.step_label)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_product_page())
        self.stack.addWidget(self._build_entry_page())
        self.stack.addWidget(self._build_confirm_page())
        self.content.addWidget(self.stack)

        # A Back button (ResetRole never auto-triggers accept/reject).
        self.back_button = QPushButton(strings.ADJUST_BACK)
        self.buttons.addButton(self.back_button, QDialogButtonBox.ButtonRole.ResetRole)
        self.back_button.clicked.connect(self._go_back)

        self._go_to(0)

    # --------------------------------------------------------------- pages

    def _build_product_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACING["sm"])
        self.search = ProductSearchBox(
            self.api,
            self.store_id,
            self._on_product_selected,
            placeholder=strings.ADJUST_SEARCH_PLACEHOLDER,
        )
        layout.addWidget(self.search)
        self.selected_label = QLabel("")
        self.selected_label.setStyleSheet("font-weight: 600; background: transparent;")
        self.selected_label.setWordWrap(True)
        layout.addWidget(self.selected_label)
        layout.addStretch(1)
        return page

    def _build_entry_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACING["md"])

        self.current_stock_label = QLabel("")
        self.current_stock_label.setStyleSheet(
            "font-weight: 600; background: transparent;"
        )
        layout.addWidget(self.current_stock_label)

        counted_label = QLabel(strings.ADJUST_COUNTED_LABEL)
        counted_label.setObjectName("Caption")
        layout.addWidget(counted_label)
        self.counted_input = QSpinBox()
        self.counted_input.setRange(0, 99_999)
        self.counted_input.valueChanged.connect(self._update_delta)
        layout.addWidget(self.counted_input)

        self.delta_label = QLabel("")
        layout.addWidget(self.delta_label)

        reason_label = QLabel(strings.ADJUST_REASON_LABEL)
        reason_label.setObjectName("Caption")
        layout.addWidget(reason_label)
        self.reason_combo = QComboBox()
        for code, label in strings.ADJUST_REASONS.items():
            self.reason_combo.addItem(label, code)
        layout.addWidget(self.reason_combo)

        note_label = QLabel(strings.ADJUST_NOTE_LABEL)
        note_label.setObjectName("Caption")
        layout.addWidget(note_label)
        self.note_input = QLineEdit()
        self.note_input.setPlaceholderText(strings.ADJUST_NOTE_PLACEHOLDER)
        layout.addWidget(self.note_input)
        layout.addStretch(1)
        return page

    def _build_confirm_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACING["md"])

        self.confirm_label = QLabel("")
        self.confirm_label.setWordWrap(True)
        self.confirm_label.setStyleSheet("background: transparent;")
        layout.addWidget(self.confirm_label)

        pin_prompt = QLabel(strings.PIN_CONFIRM_PROMPT)
        pin_prompt.setObjectName("Caption")
        layout.addWidget(pin_prompt)
        self.pin_input = QLineEdit()
        self.pin_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pin_input.setPlaceholderText(strings.LOGIN_PLACEHOLDER)
        self.pin_input.returnPressed.connect(self.accept)
        layout.addWidget(self.pin_input)
        layout.addStretch(1)
        return page

    # ------------------------------------------------------------- helpers

    def _on_product_selected(self, product: dict) -> None:
        self.product = product
        self.selected_label.setText(
            f"{product['name']} — "
            + strings.ADJUST_CURRENT_STOCK.format(qty=product["stock_quantity"])
        )
        self.current_stock_label.setText(
            strings.ADJUST_CURRENT_STOCK.format(qty=product["stock_quantity"])
        )
        self.counted_input.setValue(int(product["stock_quantity"]))
        self._update_delta()
        self._go_to(1)  # a picked product completes step 1

    def _update_delta(self) -> None:
        if self.product is None:
            return
        delta = self.counted_input.value() - int(self.product["stock_quantity"])
        if delta > 0:
            text = strings.ADJUST_DELTA_POS.format(n=delta)
            color = SEMANTIC["success"]
        elif delta < 0:
            text = strings.ADJUST_DELTA_NEG.format(n=abs(delta))
            color = SEMANTIC["danger"]
        else:
            text = strings.ADJUST_DELTA_ZERO
            color = SEMANTIC["warning_text"]
        self.delta_label.setText(text)
        self.delta_label.setStyleSheet(
            f"color: {color}; font-weight: 700; background: transparent;"
        )

    def _delta_text(self) -> str:
        delta = self.counted_input.value() - int(self.product["stock_quantity"])
        return f"+{delta}" if delta > 0 else (str(delta) if delta < 0 else "0")

    def _go_to(self, step: int) -> None:
        self._step = step
        self.stack.setCurrentIndex(step)
        titles = [
            strings.ADJUST_STEP_PRODUCT,
            strings.ADJUST_STEP_ENTRY,
            strings.ADJUST_STEP_CONFIRM,
        ]
        self.step_label.setText(titles[step])
        self.back_button.setVisible(step > 0)
        if step == 2:
            self.ok_button.setText(strings.ADJUST_CONFIRM_BUTTON)
            self.confirm_label.setText(
                strings.ADJUST_CONFIRM_SENTENCE.format(
                    product=self.product["name"],
                    old=self.product["stock_quantity"],
                    new=self.counted_input.value(),
                    delta=self._delta_text(),
                )
            )
            self.pin_input.clear()
            self.pin_input.setFocus()
        else:
            self.ok_button.setText(strings.ADJUST_NEXT)
        self.fit_to_content()

    def _go_back(self) -> None:
        if self._step > 0:
            self._go_to(self._step - 1)

    # -------------------------------------------------------------- accept

    def accept(self) -> None:
        if self._step == 0:
            if self.product is None:
                show_error(self, strings.ADJUST_SELECT_PRODUCT_FIRST)
                return
            self._go_to(1)
            return
        if self._step == 1:
            self._go_to(2)
            return
        # Step 2 — confirm with PIN.
        pin = self.pin_input.text().strip()
        if not pin:
            return
        self.ok_button.setEnabled(False)
        run_api(
            lambda: self.api.adjust_stock(
                self.product["id"],
                self.counted_input.value(),
                self.reason_combo.currentData(),
                self.note_input.text().strip() or None,
                pin,
            ),
            self._on_done,
            self._on_error,
        )

    def _on_done(self, result: object) -> None:
        self.result = result
        super().accept()

    def _on_error(self, err) -> None:
        self.ok_button.setEnabled(True)
        if err.code in ("invalid_pin", "pin_not_configured"):
            show_error(self, strings.PIN_CONFIRM_WRONG)
            self.pin_input.selectAll()
            self.pin_input.setFocus()
        else:
            show_error(self, err.message)
