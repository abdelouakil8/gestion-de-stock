"""Owner-only promotion (coupon) management — the "Promotions" settings tab.

List / create / deactivate store coupon codes. Redemption + validity are
enforced server-side at checkout; this widget only manages the catalog.
"""

import qtawesome as qta
import shiboken6
from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from services.workers import run_api
from ui import format as fmt
from ui import strings
from ui.styles.tokens import SPACING
from ui.widgets.badge import Badge
from ui.widgets.data_table import DataTable
from ui.widgets.modal import ModalDialog, ask_confirm, show_error
from ui.widgets.states import EmptyState, StatefulStack
from ui.widgets.toast import show_toast


def _type_label(promo_type: str) -> str:
    return strings.PROMO_TYPE_LABELS.get(promo_type, promo_type)


def _value_text(promo: dict) -> str:
    if promo.get("type") == "percent":
        value = str(promo.get("value", "0")).rstrip("0").rstrip(".")
        return f"{value} %"
    return fmt.fmt_money(promo.get("value", 0))


class PromotionDialog(ModalDialog):
    def __init__(self, api, store_id: str, parent=None) -> None:
        super().__init__(strings.PROMO_DIALOG_NEW, parent)
        self.api = api
        self.store_id = store_id
        self.result_promo: dict | None = None

        self.content.addWidget(QLabel(strings.PROMO_CODE))
        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText(strings.PROMO_CODE_PLACEHOLDER)
        self.content.addWidget(self.code_input)

        self.content.addWidget(QLabel(strings.PROMO_TYPE))
        self.type_combo = QComboBox()
        for value in ("percent", "fixed"):
            self.type_combo.addItem(strings.PROMO_TYPE_LABELS[value], value)
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        self.content.addWidget(self.type_combo)

        self.content.addWidget(QLabel(strings.PROMO_VALUE))
        self.value_input = QDoubleSpinBox()
        self.value_input.setDecimals(2)
        self.value_input.setRange(0.0, 9_999_999.99)
        self.content.addWidget(self.value_input)

        dates_row = QHBoxLayout()
        from_box = QVBoxLayout()
        from_box.addWidget(QLabel(strings.PROMO_VALID_FROM))
        self.from_input = QDateEdit(QDate.currentDate())
        self.from_input.setCalendarPopup(True)
        self.from_input.setDisplayFormat("dd/MM/yyyy")
        from_box.addWidget(self.from_input)
        dates_row.addLayout(from_box)
        to_box = QVBoxLayout()
        to_box.addWidget(QLabel(strings.PROMO_VALID_TO))
        self.to_input = QDateEdit(QDate.currentDate().addDays(30))
        self.to_input.setCalendarPopup(True)
        self.to_input.setDisplayFormat("dd/MM/yyyy")
        to_box.addWidget(self.to_input)
        dates_row.addLayout(to_box)
        self.content.addLayout(dates_row)

        self.content.addWidget(QLabel(strings.PROMO_MAX_USES))
        self.max_uses_input = QSpinBox()
        self.max_uses_input.setRange(0, 1_000_000)
        self.max_uses_input.setSpecialValueText(strings.PROMO_UNLIMITED)  # 0
        self.content.addWidget(self.max_uses_input)

        self._on_type_changed()
        self.code_input.setFocus()

    def _on_type_changed(self) -> None:
        if self.type_combo.currentData() == "percent":
            self.value_input.setSuffix(" %")
            self.value_input.setMaximum(100.0)
        else:
            self.value_input.setSuffix("")
            self.value_input.setMaximum(9_999_999.99)

    def accept(self) -> None:
        code = self.code_input.text().strip()
        if not code:
            show_error(self, strings.REQUIRED_FIELD)
            return
        if self.value_input.value() <= 0:
            show_error(self, strings.PROMO_VALUE_REQUIRED)
            return
        if self.from_input.date() > self.to_input.date():
            show_error(self, strings.PROMO_DATE_ORDER)
            return
        max_uses = self.max_uses_input.value()
        payload = {
            "store_id": self.store_id,
            "code": code,
            "type": self.type_combo.currentData(),
            "value": f"{self.value_input.value():.2f}",
            "valid_from": self.from_input.date().toString("yyyy-MM-dd") + "T00:00:00",
            "valid_to": self.to_input.date().toString("yyyy-MM-dd") + "T23:59:59",
            "max_uses": max_uses if max_uses > 0 else None,
        }
        self.ok_button.setEnabled(False)
        run_api(
            lambda: self.api.create_promotion(payload),
            self._on_saved,
            self._on_error,
        )

    def _on_saved(self, promo: object) -> None:
        self.result_promo = promo
        super().accept()

    def _on_error(self, err) -> None:
        self.ok_button.setEnabled(True)
        show_error(self, err.message)


class PromotionsManagementTab(QWidget):
    def __init__(self, api, store_id: str, parent=None) -> None:
        super().__init__(parent)
        self.api = api
        self.store_id = store_id
        self.promotions: list[dict] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACING["md"])

        toolbar = QHBoxLayout()
        title = QLabel(strings.SETTINGS_TAB_PROMOTIONS)
        title.setObjectName("SectionTitle")
        toolbar.addWidget(title)
        toolbar.addStretch(1)
        new_button = QPushButton(
            qta.icon("fa5s.plus", color="white"), strings.PROMO_NEW
        )
        new_button.setObjectName("Primary")
        new_button.clicked.connect(self._create)
        self.deactivate_button = QPushButton(strings.PROMO_DEACTIVATE)
        self.deactivate_button.setObjectName("Danger")
        self.deactivate_button.clicked.connect(self._deactivate)
        self.deactivate_button.setEnabled(False)
        toolbar.addWidget(new_button)
        toolbar.addWidget(self.deactivate_button)
        layout.addLayout(toolbar)

        self.table = DataTable(
            [
                strings.PROMO_COL_CODE,
                strings.PROMO_COL_TYPE,
                strings.PROMO_COL_VALUE,
                strings.PROMO_COL_VALIDITY,
                strings.PROMO_COL_USES,
                strings.PROMO_COL_STATUS,
            ]
        )
        self.table.itemSelectionChanged.connect(self._on_selection)
        self.stack = StatefulStack(
            self.table, EmptyState("fa5s.tags", strings.PROMO_EMPTY)
        )
        layout.addWidget(self.stack, stretch=1)

    def refresh(self) -> None:
        self.stack.show_loading()
        run_api(
            lambda: self.api.list_promotions(self.store_id),
            self._on_loaded,
            self._on_error,
        )

    def _on_loaded(self, promotions: object) -> None:
        if not shiboken6.isValid(self):
            return
        self.promotions = list(promotions or [])
        if not self.promotions:
            self.stack.show_empty()
            return
        self.table.set_rows(
            [
                [
                    p["code"],
                    _type_label(p["type"]),
                    _value_text(p),
                    strings.PROMO_VALIDITY_RANGE.format(
                        start=fmt.fmt_date(p["valid_from"]),
                        end=fmt.fmt_date(p["valid_to"]),
                    ),
                    self._uses_text(p),
                    "",  # status badge
                ]
                for p in self.promotions
            ]
        )
        for row, promo in enumerate(self.promotions):
            holder = QWidget()
            box = QHBoxLayout(holder)
            box.setContentsMargins(SPACING["xs"], 2, SPACING["xs"], 2)
            active = promo.get("is_active", True)
            box.addWidget(
                Badge(
                    strings.PROMO_ACTIVE if active else strings.PROMO_INACTIVE,
                    "success" if active else "neutral",
                )
            )
            box.addStretch(1)
            self.table.setCellWidget(row, 5, holder)
        self.stack.show_content()

    @staticmethod
    def _uses_text(promo: dict) -> str:
        used = promo.get("used_count", 0)
        max_uses = promo.get("max_uses")
        return f"{used} / {max_uses}" if max_uses else f"{used} / ∞"

    def _on_error(self, err) -> None:
        if not shiboken6.isValid(self):
            return
        self.stack.show_empty()
        show_error(self, err.message)

    # ------------------------------------------------------------- actions

    def _selected(self) -> dict | None:
        row = self.table.selected_row()
        if 0 <= row < len(self.promotions):
            return self.promotions[row]
        return None

    def _on_selection(self) -> None:
        promo = self._selected()
        self.deactivate_button.setEnabled(
            promo is not None and promo.get("is_active", True)
        )

    def _create(self) -> None:
        dialog = PromotionDialog(self.api, self.store_id, parent=self)
        if dialog.exec() and dialog.result_promo:
            self.refresh()
            show_toast(self, strings.PROMO_SAVED_TOAST)

    def _deactivate(self) -> None:
        promo = self._selected()
        if not promo:
            return
        if not ask_confirm(
            self, strings.PROMO_DEACTIVATE_CONFIRM.format(code=promo["code"])
        ):
            return
        run_api(
            lambda: self.api.deactivate_promotion(promo["id"]),
            lambda _result: self._on_deactivated(),
            self._on_error,
        )

    def _on_deactivated(self) -> None:
        self.refresh()
        show_toast(self, strings.PROMO_DEACTIVATED_TOAST)
