"""Inventory screen — list/search/filter, create/edit/archive, images,
named price levels with live ordering hints, and a product detail view
(double-click) with per-product statistics.

All mutations are owner actions: the API enforces the PIN server-side (the
client attaches the PIN captured at app open). cost_price is only fetched
through the owner endpoint, never present in cashier-facing data.
"""

from decimal import Decimal
from pathlib import Path

import qtawesome as qta
import shiboken6
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from services import image_cache
from services.workers import run_api
from ui import format as fmt
from ui import strings
from ui.styles.tokens import ICON_SIZES, NEUTRAL, SEMANTIC, SPACING, THUMB_SIZES
from ui.widgets.badge import Badge
from ui.widgets.bars import BarChart
from ui.widgets.data_table import DataTable
from ui.widgets.modal import ModalDialog, ask_confirm, show_error
from ui.widgets.states import EmptyState, StatefulStack
from ui.widgets.stock_adjust_dialog import StockAdjustDialog
from ui.widgets.stock_movements_view import StockMovementsView
from ui.widgets.thumb import Thumb
from ui.widgets.toast import show_toast

_CONTENT_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


# Shared column widths so the packaging header row and each editable row
# line up (a plain QHBoxLayout of fixed-width fields aligns predictably).
_PK_W_LABEL = 150
_PK_W_UNITS = 90
_PK_W_PRICE = 95
_PK_W_REMOVE = 30


class _PackagingRow(QWidget):
    """One editable packaging (carton) inside the product form: label,
    units-per-package, and its own three named prices."""

    def __init__(self, on_remove, on_change, data: dict | None = None) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACING["xs"])

        self.label_input = QLineEdit()
        self.label_input.setPlaceholderText(strings.PACKAGING_LABEL)
        self.label_input.setFixedWidth(_PK_W_LABEL)
        self.unit_count = QSpinBox()
        self.unit_count.setRange(1, 1_000_000)
        self.unit_count.setValue(1)
        self.unit_count.setPrefix("×")
        self.unit_count.setFixedWidth(_PK_W_UNITS)
        self.unit_count.setToolTip(strings.PACKAGING_UNIT_COUNT)
        self.detail = self._money(strings.PRICE_DETAIL)
        self.gros = self._money(strings.PRICE_GROS)
        self.super_gros = self._money(strings.PRICE_SUPER_GROS)

        layout.addWidget(self.label_input)
        layout.addWidget(self.unit_count)
        layout.addWidget(self.detail)
        layout.addWidget(self.gros)
        layout.addWidget(self.super_gros)
        remove = QPushButton(qta.icon("fa5s.times", color=NEUTRAL["500"]), "")
        remove.setObjectName("Ghost")
        remove.setFixedWidth(_PK_W_REMOVE)
        remove.setToolTip(strings.PACKAGING_REMOVE)
        remove.clicked.connect(lambda: on_remove(self))
        layout.addWidget(remove)
        layout.addStretch(1)

        for widget in (self.detail, self.gros, self.super_gros, self.unit_count):
            widget.valueChanged.connect(lambda _=None: on_change())

        if data:
            self.label_input.setText(data.get("label", ""))
            self.unit_count.setValue(int(data.get("unit_count", 1)))
            self.detail.setValue(float(data.get("price_detail", 0)))
            self.gros.setValue(float(data.get("price_gros", 0)))
            self.super_gros.setValue(float(data.get("price_super_gros", 0)))

    @staticmethod
    def _money(placeholder: str) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setDecimals(2)
        spin.setMaximum(9_999_999.99)
        spin.setFixedWidth(_PK_W_PRICE)
        spin.setToolTip(placeholder)
        return spin

    @staticmethod
    def build_header() -> QWidget:
        """A column-header row aligned with the editable fields above."""
        header = QWidget()
        row = QHBoxLayout(header)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(SPACING["xs"])

        def cap(text: str, width: int) -> QLabel:
            label = QLabel(text)
            label.setObjectName("Caption")
            label.setFixedWidth(width)
            return label

        row.addWidget(cap(strings.PACKAGING_LABEL_COL, _PK_W_LABEL))
        row.addWidget(cap(strings.PACKAGING_UNITS_COL, _PK_W_UNITS))
        row.addWidget(cap(strings.PRICE_DETAIL, _PK_W_PRICE))
        row.addWidget(cap(strings.PRICE_GROS, _PK_W_PRICE))
        row.addWidget(cap(strings.PRICE_SUPER_GROS, _PK_W_PRICE))
        row.addStretch(1)
        return header

    def is_blank(self) -> bool:
        return not self.label_input.text().strip()

    def order_ok(self) -> bool:
        return self.detail.value() >= self.gros.value() >= self.super_gros.value()

    def payload(self, position: int) -> dict:
        return {
            "label": self.label_input.text().strip(),
            "unit_count": self.unit_count.value(),
            "price_detail": f"{self.detail.value():.2f}",
            "price_gros": f"{self.gros.value():.2f}",
            "price_super_gros": f"{self.super_gros.value():.2f}",
            "position": position,
        }


class ProductDialog(ModalDialog):
    """Create/edit product form. `details` present ⇒ edit mode (owner data).

    Price-level ordering (détail ≥ gros ≥ super gros) is hinted LIVE here
    and enforced authoritatively by the server on save."""

    def __init__(self, api, store_id, categories, details=None, parent=None) -> None:
        title = strings.PRODUCT_DIALOG_EDIT if details else strings.PRODUCT_DIALOG_NEW
        super().__init__(title, parent)
        self.api = api
        self.store_id = store_id
        self.details = details
        self.result_product: dict | None = None
        self._staged_image: Path | None = None
        self._staged_removal = False
        # Wider than the base dialog so the packaging columns (name + units +
        # 3 prices) fit on one line without overflowing.
        self.setMinimumWidth(680)

        form = QFormLayout()
        form.setSpacing(SPACING["md"])

        self.name_input = QLineEdit()
        self.barcode_input = QLineEdit()
        self.category_combo = QComboBox()
        self.category_combo.addItem(strings.PRODUCT_NO_CATEGORY, None)
        for category in categories:
            self.category_combo.addItem(category["name"], category["id"])
        self.category_combo.addItem(strings.PRODUCT_NEW_CATEGORY, "__new__")
        self.category_combo.currentIndexChanged.connect(self._maybe_new_category)

        def money_spin() -> QDoubleSpinBox:
            spin = QDoubleSpinBox()
            spin.setDecimals(2)
            spin.setMaximum(9_999_999.99)
            spin.valueChanged.connect(self._check_price_order)
            return spin

        self.cost_input = money_spin()
        self.detail_input = money_spin()
        self.gros_input = money_spin()
        self.super_gros_input = money_spin()
        self.stock_input = QSpinBox()
        self.stock_input.setRange(0, 1_000_000)
        self.threshold_input = QSpinBox()
        self.threshold_input.setRange(0, 1_000_000)
        self.threshold_input.setValue(5)
        self.active_check = QCheckBox(strings.PRODUCT_ACTIVE)
        self.active_check.setChecked(True)

        form.addRow(strings.PRODUCT_NAME, self.name_input)

        barcode_row = QHBoxLayout()
        barcode_row.setContentsMargins(0, 0, 0, 0)
        barcode_row.addWidget(self.barcode_input, stretch=1)
        self.btn_print_label = QPushButton(
            qta.icon("fa5s.barcode", color=NEUTRAL["600"]), strings.PRODUCT_PRINT_LABEL
        )
        self.btn_print_label.clicked.connect(self._print_label)
        self.btn_print_label.setEnabled(bool(details))
        barcode_row.addWidget(self.btn_print_label)
        form.addRow(strings.PRODUCT_BARCODE, barcode_row)
        form.addRow(strings.PRODUCT_CATEGORY, self.category_combo)
        form.addRow(strings.PRODUCT_COST_PRICE, self.cost_input)
        form.addRow(strings.PRODUCT_PRICE_DETAIL, self.detail_input)
        form.addRow(strings.PRODUCT_PRICE_GROS, self.gros_input)
        form.addRow(strings.PRODUCT_PRICE_SUPER_GROS, self.super_gros_input)

        self.order_hint = QLabel(strings.PRODUCT_PRICE_ORDER_HINT)
        self.order_hint.setObjectName("FieldHint")
        self.order_hint.setWordWrap(True)
        form.addRow("", self.order_hint)

        form.addRow(strings.PRODUCT_STOCK, self.stock_input)
        form.addRow(strings.PRODUCT_LOW_STOCK_THRESHOLD, self.threshold_input)
        form.addRow("", self.active_check)

        # Image picker with preview.
        image_row = QHBoxLayout()
        self.image_preview = Thumb(THUMB_SIZES["preview"])
        image_row.addWidget(self.image_preview)
        image_buttons = QVBoxLayout()
        choose_button = QPushButton(
            qta.icon("fa5s.image", color=NEUTRAL["600"]), strings.PRODUCT_IMAGE_CHOOSE
        )
        choose_button.clicked.connect(self._choose_image)
        self.remove_image_button = QPushButton(strings.PRODUCT_IMAGE_REMOVE)
        self.remove_image_button.setObjectName("Ghost")
        self.remove_image_button.clicked.connect(self._remove_image)
        image_buttons.addWidget(choose_button)
        image_buttons.addWidget(self.remove_image_button)
        image_buttons.addStretch(1)
        image_row.addLayout(image_buttons)
        image_row.addStretch(1)
        form.addRow(strings.PRODUCT_IMAGE, image_row)

        self.content.addLayout(form)

        # --------------------------------------------- packagings (cartons)
        packaging_title = QLabel(strings.PRODUCT_PACKAGINGS)
        packaging_title.setObjectName("SectionTitle")
        self.content.addWidget(packaging_title)
        packaging_hint = QLabel(strings.PACKAGING_HINT)
        packaging_hint.setObjectName("FieldHint")
        packaging_hint.setWordWrap(True)
        self.content.addWidget(packaging_hint)
        # Column header (hidden until at least one packaging row exists).
        self._packaging_header = _PackagingRow.build_header()
        self._packaging_header.hide()
        self.content.addWidget(self._packaging_header)
        self._packaging_rows: list[_PackagingRow] = []
        self._packaging_box = QVBoxLayout()
        self._packaging_box.setSpacing(SPACING["xs"])
        self.content.addLayout(self._packaging_box)
        add_packaging = QPushButton(
            qta.icon("fa5s.plus", color=NEUTRAL["600"]), strings.PACKAGING_ADD
        )
        add_packaging.setObjectName("Ghost")
        add_packaging.clicked.connect(lambda: self._add_packaging_row())
        self.content.addWidget(add_packaging)

        if details:
            self.name_input.setText(details["name"])
            self.barcode_input.setText(details.get("barcode") or "")
            index = self.category_combo.findData(details.get("category_id"))
            if index >= 0:
                self.category_combo.setCurrentIndex(index)
            self.cost_input.setValue(float(details["cost_price"]))
            self.detail_input.setValue(float(details["price_detail"]))
            self.gros_input.setValue(float(details["price_gros"]))
            self.super_gros_input.setValue(float(details["price_super_gros"]))
            self.stock_input.setValue(details["stock_quantity"])
            self.threshold_input.setValue(details.get("low_stock_threshold", 5))
            self.active_check.setChecked(details["is_active"])
            self.image_preview.set_product(details)
            self.remove_image_button.setVisible(bool(details.get("image_path")))
            for packaging in details.get("packagings") or []:
                self._add_packaging_row(packaging)
        else:
            self.image_preview.set_letter("")
            self.remove_image_button.hide()
        self._check_price_order()

    # ---------------------------------------------------------- packagings

    def _print_label(self) -> None:
        if not self.details:
            return
        from services import label_printer, printing

        printer = printing.get_selected_printer()

        product = dict(self.details)
        product["name"] = self.name_input.text()
        product["barcode"] = self.barcode_input.text()
        product["price_detail"] = self.detail_input.value()

        try:
            label_printer.print_barcode_label(product, printer, copies=1)
            from ui.widgets.toast import show_toast

            show_toast(self, "Étiquette envoyée à l'imprimante.")
        except Exception as e:
            from ui.widgets.modal import show_error

            show_error(self, strings.ERROR_TITLE, f"Erreur d'impression : {e}")

    def _add_packaging_row(self, data: dict | None = None) -> None:
        row = _PackagingRow(self._remove_packaging_row, self._check_price_order, data)
        self._packaging_rows.append(row)
        self._packaging_box.addWidget(row)
        self._packaging_header.setVisible(bool(self._packaging_rows))
        self.fit_to_content()

    def _remove_packaging_row(self, row: "_PackagingRow") -> None:
        if row in self._packaging_rows:
            self._packaging_rows.remove(row)
        self._packaging_box.removeWidget(row)
        row.deleteLater()
        self._packaging_header.setVisible(bool(self._packaging_rows))
        self.fit_to_content()

    def _packagings_payload(self) -> list[dict] | None:
        """Full current packaging list (position = row order); None if a row
        has an invalid price order (caller shows the error)."""
        payload = []
        position = 0
        for row in self._packaging_rows:
            if row.is_blank():
                continue
            if not row.order_ok():
                return None
            payload.append(row.payload(position))
            position += 1
        return payload

    # ------------------------------------------------------------- image

    def _choose_image(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(
            self, strings.PRODUCT_IMAGE_CHOOSE, "", strings.PRODUCT_IMAGE_FILTER
        )
        if not path_str:
            return
        path = Path(path_str)
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            show_error(self, strings.UNEXPECTED_ERROR)
            return
        self._staged_image = path
        self._staged_removal = False
        self.image_preview.set_pixmap_direct(pixmap, self.name_input.text())
        self.remove_image_button.show()

    def _remove_image(self) -> None:
        self._staged_image = None
        self._staged_removal = bool(self.details and self.details.get("image_path"))
        self.image_preview.set_letter(self.name_input.text())
        self.remove_image_button.hide()

    # ---------------------------------------------------------- categories

    def _maybe_new_category(self) -> None:
        if self.category_combo.currentData() != "__new__":
            return
        name, ok = QInputDialog.getText(
            self, strings.PRODUCT_NEW_CATEGORY, strings.PRODUCT_NEW_CATEGORY_PROMPT
        )
        if not (ok and name.strip()):
            self.category_combo.setCurrentIndex(0)
            return
        self.category_combo.setEnabled(False)
        run_api(
            lambda: self.api.create_category(self.store_id, name.strip()),
            self._on_category_created,
            self._on_category_error,
        )

    def _on_category_created(self, category: object) -> None:
        self.category_combo.setEnabled(True)
        index = self.category_combo.count() - 1  # before the "new…" entry
        self.category_combo.insertItem(index, category["name"], category["id"])
        self.category_combo.setCurrentIndex(index)

    def _on_category_error(self, err) -> None:
        self.category_combo.setEnabled(True)
        self.category_combo.setCurrentIndex(0)
        show_error(self, err.message)

    # ------------------------------------------------------------- pricing

    def _price_order_ok(self) -> bool:
        return (
            self.detail_input.value()
            >= self.gros_input.value()
            >= self.super_gros_input.value()
        )

    def _check_price_order(self) -> None:
        if self._price_order_ok():
            self.order_hint.setText(strings.PRODUCT_PRICE_ORDER_HINT)
            self.order_hint.setObjectName("FieldHint")
        else:
            self.order_hint.setText(strings.PRODUCT_PRICE_ORDER_ERROR)
            self.order_hint.setObjectName("FieldError")
        self.order_hint.style().unpolish(self.order_hint)
        self.order_hint.style().polish(self.order_hint)

    # -------------------------------------------------------------- saving

    def accept(self) -> None:  # validation + API call, stays open on error
        name = self.name_input.text().strip()
        if not name:
            show_error(self, strings.REQUIRED_FIELD)
            return
        if not self._price_order_ok():
            show_error(self, strings.PRODUCT_PRICE_ORDER_ERROR)
            return
        packagings = self._packagings_payload()
        if packagings is None:
            show_error(self, strings.PRODUCT_PRICE_ORDER_ERROR)
            return
        payload = {
            "name": name,
            "barcode": self.barcode_input.text().strip() or None,
            "category_id": self.category_combo.currentData(),
            "cost_price": f"{self.cost_input.value():.2f}",
            "price_detail": f"{self.detail_input.value():.2f}",
            "price_gros": f"{self.gros_input.value():.2f}",
            "price_super_gros": f"{self.super_gros_input.value():.2f}",
            "stock_quantity": self.stock_input.value(),
            "low_stock_threshold": self.threshold_input.value(),
            "is_active": self.active_check.isChecked(),
            # Full current packaging set (empty list clears them).
            "packagings": packagings,
        }
        self.ok_button.setEnabled(False)
        if self.details:
            product_id = self.details["id"]
            call = lambda: self.api.update_product(product_id, payload)  # noqa: E731
        else:
            payload["store_id"] = self.store_id
            call = lambda: self.api.create_product(payload)  # noqa: E731
        run_api(call, self._on_saved, self._on_save_error)

    def _on_saved(self, product: object) -> None:
        self.result_product = product
        product_id = product["id"]
        image_cache.invalidate(product_id)
        # Stage 2: apply the image change (best-effort; product is saved).
        if self._staged_image is not None:
            path = self._staged_image
            content_type = _CONTENT_TYPES.get(path.suffix.lower())
            try:
                data = path.read_bytes()
            except OSError as exc:
                show_error(
                    self,
                    strings.PRODUCT_IMAGE_UPLOAD_FAILED.format(reason=exc),
                )
                super().accept()
                return
            run_api(
                lambda: self.api.upload_product_image(
                    product_id, data, content_type or "image/png", path.name
                ),
                lambda _: self._finish(),
                self._on_image_error,
            )
        elif self._staged_removal:
            run_api(
                lambda: self.api.delete_product_image(product_id),
                lambda _: self._finish(),
                self._on_image_error,
            )
        else:
            self._finish()

    def _finish(self) -> None:
        if self.result_product is not None:
            image_cache.invalidate(self.result_product["id"])
        super().accept()

    def _on_image_error(self, err) -> None:
        show_error(self, strings.PRODUCT_IMAGE_UPLOAD_FAILED.format(reason=err.message))
        super().accept()  # the product itself was saved

    def _on_save_error(self, err) -> None:
        self.ok_button.setEnabled(True)
        show_error(self, err.message)


def _movement_type_label(key: str) -> str:
    return {
        "sale": strings.MOVEMENT_TYPE_SALE,
        "purchase": strings.MOVEMENT_TYPE_PURCHASE,
        "refund": strings.MOVEMENT_TYPE_REFUND,
        "adjustment": strings.MOVEMENT_TYPE_ADJUSTMENT,
    }.get(key, key)


# Movement type → Badge kind: sale red, purchase green, refund amber,
# adjustment blue (accent).
_MOVEMENT_KIND = {
    "sale": "danger",
    "purchase": "success",
    "refund": "warning",
    "adjustment": "accent",
}


class _MovementRow(QFrame):
    """One ledger entry: date, type badge, signed delta, resulting stock."""

    def __init__(self, mv: dict) -> None:
        super().__init__()
        self.setObjectName("RuleCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(
            SPACING["md"], SPACING["sm"], SPACING["md"], SPACING["sm"]
        )
        outer.setSpacing(2)

        top = QHBoxLayout()
        top.setSpacing(SPACING["md"])
        date = QLabel(fmt.fmt_short_datetime(mv.get("created_at")))
        date.setObjectName("Muted")
        top.addWidget(date)

        mtype = mv.get("movement_type", "")
        top.addWidget(
            Badge(_movement_type_label(mtype), _MOVEMENT_KIND.get(mtype, "neutral"))
        )

        delta = int(mv.get("quantity_delta", 0) or 0)
        top.addWidget(self._delta_widget(delta))
        top.addStretch(1)

        after = QLabel(
            strings.MOVEMENT_STOCK_AFTER.format(qty=mv.get("quantity_after", ""))
        )
        after.setObjectName("Muted")
        top.addWidget(after)
        outer.addLayout(top)

        note = mv.get("note")
        if note:
            note_label = QLabel(note)
            note_label.setObjectName("Muted")
            note_label.setWordWrap(True)
            font = note_label.font()
            font.setItalic(True)
            note_label.setFont(font)
            outer.addWidget(note_label)

    @staticmethod
    def _delta_widget(delta: int) -> QWidget:
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(2)
        up = delta >= 0
        color = SEMANTIC["success"] if up else SEMANTIC["danger"]
        icon = QLabel()
        icon.setPixmap(
            qta.icon("fa5s.arrow-up" if up else "fa5s.arrow-down", color=color).pixmap(
                ICON_SIZES["sm"], ICON_SIZES["sm"]
            )
        )
        icon.setStyleSheet("background: transparent;")
        row.addWidget(icon)
        if delta > 0:
            text = f"+{delta}"
        elif delta < 0:
            text = f"−{abs(delta)}"  # U+2212 minus, matching the spec
        else:
            text = "0"
        label = QLabel(text)
        label.setStyleSheet(
            f"color: {color}; font-weight: 700; background: transparent;"
        )
        row.addWidget(label)
        return holder


class ProductDetailDialog(ModalDialog):
    """Read-only product sheet: Informations (stats) + Historique (ledger)."""

    def __init__(self, api, store_id: str, product: dict, parent=None) -> None:
        super().__init__(strings.PRODUCT_DETAIL_TITLE, parent)
        self.api = api
        self.store_id = store_id
        self.product = product
        self._hist_limit = 20
        self._hist_loaded = False
        self.setMinimumWidth(640)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_info_tab(product), strings.PRODUCT_TAB_INFO)
        self.tabs.addTab(self._build_history_tab(), strings.PRODUCT_TAB_HISTORY)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.content.addWidget(self.tabs)

        self.cancel_button.hide()
        self.ok_button.setText(strings.CLOSE)

        # Stats power the Informations tab (shown first) — load immediately.
        run_api(
            lambda: self.api.stats_product(store_id, product["id"]),
            self._on_stats,
            self._on_stats_error,
        )

    # ---------------------------------------------------- Informations tab

    def _build_info_tab(self, product: dict) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACING["md"])

        header = QHBoxLayout()
        header.setSpacing(SPACING["lg"])
        thumb = Thumb(THUMB_SIZES["detail"])
        thumb.set_product(product)
        header.addWidget(thumb)

        info = QVBoxLayout()
        name = QLabel(product["name"])
        name.setObjectName("ScreenTitle")
        info.addWidget(name)
        barcode = QLabel(product.get("barcode") or "—")
        barcode.setObjectName("Muted")
        info.addWidget(barcode)

        chips = QHBoxLayout()
        chips.setSpacing(SPACING["sm"])
        chips.addWidget(
            Badge(
                f"{strings.PRICE_DETAIL} {fmt.fmt_money(product['price_detail'])}",
                "accent",
            )
        )
        chips.addWidget(
            Badge(
                f"{strings.PRICE_GROS} {fmt.fmt_money(product['price_gros'])}",
                "neutral",
            )
        )
        chips.addWidget(
            Badge(
                f"{strings.PRICE_SUPER_GROS} "
                f"{fmt.fmt_money(product['price_super_gros'])}",
                "neutral",
            )
        )
        stock = product["stock_quantity"]
        low = stock <= product.get("low_stock_threshold", 5)
        chips.addWidget(
            Badge(
                f"{strings.INVENTORY_COL_STOCK} {stock}",
                "danger" if low else "success",
            )
        )
        chips.addStretch(1)
        info.addLayout(chips)
        info.addStretch(1)
        header.addLayout(info, stretch=1)
        layout.addLayout(header)

        stats_title = QLabel(strings.PRODUCT_DETAIL_STATS)
        stats_title.setObjectName("SectionTitle")
        layout.addWidget(stats_title)

        self.stats_grid = QGridLayout()
        self.stats_grid.setSpacing(SPACING["sm"])
        layout.addLayout(self.stats_grid)

        self.chart = BarChart()
        layout.addWidget(self.chart, stretch=1)

        self.loading = QLabel(strings.LOADING + "…")
        self.loading.setObjectName("Muted")
        layout.addWidget(self.loading)
        return page

    # ------------------------------------------------------- Historique tab

    def _build_history_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACING["sm"])

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(SPACING["sm"])
        self._hist_holder = QWidget()
        self._hist_box = QVBoxLayout(self._hist_holder)
        self._hist_box.setContentsMargins(0, 0, 0, 0)
        self._hist_box.setSpacing(SPACING["sm"])
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._hist_holder)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content_layout.addWidget(scroll, stretch=1)
        self._voir_plus = QPushButton(strings.MOVEMENT_LOAD_MORE)
        self._voir_plus.setObjectName("Secondary")
        self._voir_plus.clicked.connect(self._load_more)
        self._voir_plus.hide()
        content_layout.addWidget(
            self._voir_plus, alignment=Qt.AlignmentFlag.AlignCenter
        )

        self._hist_stack = StatefulStack(
            content, EmptyState("fa5s.history", strings.MOVEMENT_EMPTY)
        )
        layout.addWidget(self._hist_stack, stretch=1)
        return page

    def _on_tab_changed(self, index: int) -> None:
        if index == 1 and not self._hist_loaded:
            self._load_history()

    def _load_history(self) -> None:
        self._hist_stack.show_loading()
        run_api(
            lambda: self.api.get_product_movements(
                self.store_id, self.product["id"], limit=self._hist_limit
            ),
            self._on_movements,
            self._on_movements_error,
        )

    def _load_more(self) -> None:
        self._hist_limit *= 2
        self._load_history()

    def _on_movements(self, page: object) -> None:
        if not shiboken6.isValid(self):
            return
        self._hist_loaded = True
        items = page.get("items", []) if isinstance(page, dict) else []
        total = page.get("total", len(items)) if isinstance(page, dict) else len(items)
        while self._hist_box.count():
            row = self._hist_box.takeAt(0)
            if row.widget() is not None:
                row.widget().deleteLater()
        for mv in items:
            self._hist_box.addWidget(_MovementRow(mv))
        self._hist_box.addStretch(1)
        # "Voir plus": more rows exist than we've loaded.
        self._voir_plus.setVisible(len(items) < total)
        if items:
            self._hist_stack.show_content()
        else:
            self._hist_stack.show_empty()

    def _on_movements_error(self, err) -> None:
        if not shiboken6.isValid(self):
            return
        self._hist_loaded = True
        self._hist_stack.show_empty()

    # ---------------------------------------------------------- stats load

    def _on_stats(self, stats: object) -> None:
        self.loading.hide()
        headers = [
            "",
            strings.PRODUCT_STAT_UNITS,
            strings.PRODUCT_STAT_REVENUE,
            strings.PRODUCT_STAT_PROFIT,
        ]
        for col, text in enumerate(headers):
            label = QLabel(text)
            label.setObjectName("Caption")
            self.stats_grid.addWidget(label, 0, col)
        chart_data = []
        for row, period in enumerate(stats["periods"], start=1):
            period_label = strings.PERIOD_LABELS.get(period["period"], period["period"])
            name = QLabel(period_label)
            name.setStyleSheet("font-weight: 600;")
            self.stats_grid.addWidget(name, row, 0)
            self.stats_grid.addWidget(QLabel(str(period["units_sold"])), row, 1)
            self.stats_grid.addWidget(QLabel(fmt.fmt_money(period["revenue"])), row, 2)
            self.stats_grid.addWidget(QLabel(fmt.fmt_money(period["profit"])), row, 3)
            if period["period"] != "all_time":
                chart_data.append((period_label, Decimal(period["revenue"])))
        self.chart.set_data(chart_data)

    def _on_stats_error(self, err) -> None:
        if err.code in ("invalid_pin", "pin_not_configured"):
            self.loading.setText(strings.STATS_PIN_REQUIRED)
        else:
            self.loading.setText(err.message)


class InventoryScreen(QWidget):
    def __init__(self, api, store_id: str, parent=None) -> None:
        super().__init__(parent)
        self.api = api
        self.store_id = store_id
        self.products: list[dict] = []
        self.categories: list[dict] = []
        self.visible_products: list[dict] = []
        self._pending_focus: str | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(*[SPACING["xl"]] * 4)
        layout.setSpacing(SPACING["md"])

        header = QHBoxLayout()
        title = QLabel(strings.INVENTORY_TITLE)
        title.setObjectName("ScreenTitle")
        header.addWidget(title)
        hint = QLabel(strings.INVENTORY_DETAIL_HINT)
        hint.setObjectName("Muted")
        header.addWidget(hint)
        header.addStretch(1)
        layout.addLayout(header)

        toolbar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setObjectName("SearchInput")
        self.search.setPlaceholderText(strings.SEARCH)
        self.search.textChanged.connect(self._on_search_changed)
        toolbar.addWidget(self.search, stretch=1)

        new_button = QPushButton(
            qta.icon("fa5s.plus", color="white"), strings.INVENTORY_NEW_PRODUCT
        )
        new_button.setObjectName("Primary")
        new_button.clicked.connect(self._create_product)
        self.edit_button = QPushButton(
            qta.icon("fa5s.pen", color=NEUTRAL["600"]), strings.INVENTORY_EDIT_PRODUCT
        )
        self.edit_button.clicked.connect(self._edit_product)
        self.archive_button = QPushButton(strings.INVENTORY_ARCHIVE_PRODUCT)
        self.archive_button.setObjectName("Danger")
        self.archive_button.clicked.connect(self._archive_product)
        import_button = QPushButton(
            qta.icon("fa5s.file-upload", color=NEUTRAL["600"]),
            strings.IMPORT_BUTTON,
        )
        import_button.clicked.connect(self._import_csv)
        self.receive_button = QPushButton(
            qta.icon("fa5s.arrow-down", color=NEUTRAL["600"]), "Réceptionner"
        )
        self.receive_button.clicked.connect(self._receive_stock)
        # Manual stock adjustment (owner, PIN-gated) — the product is chosen
        # inside the dialog, so this action never depends on a table selection.
        self.adjust_button = QPushButton(
            qta.icon("fa5s.clipboard-check", color=NEUTRAL["600"]),
            strings.INVENTORY_ADJUST_BUTTON,
        )
        self.adjust_button.clicked.connect(self._adjust_stock)
        self.labels_button = QPushButton(
            qta.icon("fa5s.tag", color=NEUTRAL["600"]),
            strings.INVENTORY_LABELS_BUTTON,
        )
        self.labels_button.clicked.connect(self._open_label_printing)

        # Error prevention: row-dependent actions stay disabled until a row
        # is selected instead of scolding with a dialog after the click.
        self.edit_button.setEnabled(False)
        self.archive_button.setEnabled(False)
        self.receive_button.setEnabled(False)
        for button in (
            new_button,
            import_button,
            self.adjust_button,
            self.labels_button,
            self.receive_button,
            self.edit_button,
            self.archive_button,
        ):
            toolbar.addWidget(button)

        # Debounced server-side smart search (accent/Arabic/typo tolerant).
        self._search_debounce = QTimer(self)
        self._search_debounce.setSingleShot(True)
        self._search_debounce.setInterval(250)
        self._search_debounce.timeout.connect(self._run_search)
        # None = no active query (show the full catalog for the category).
        self.search_results: list[dict] | None = None

        # Body: category rail (left) + product table stack (right).
        body = QHBoxLayout()
        body.setSpacing(SPACING["md"])
        self.category_rail = QListWidget()
        self.category_rail.setObjectName("CategoryRail")
        self.category_rail.setFixedWidth(200)
        self.category_rail.currentRowChanged.connect(lambda _: self._render())
        body.addWidget(self.category_rail)

        self.table = DataTable(
            [
                "",  # thumbnail
                strings.INVENTORY_COL_NAME,
                strings.INVENTORY_COL_BARCODE,
                strings.INVENTORY_COL_CATEGORY,
                strings.INVENTORY_COL_STOCK,
                strings.INVENTORY_COL_DETAIL,
                strings.INVENTORY_COL_GROS,
                strings.INVENTORY_COL_SUPER_GROS,
                strings.INVENTORY_COL_ACTIVE,
            ]
        )
        from PySide6.QtWidgets import QHeaderView

        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Fixed
        )
        self.table.setColumnWidth(0, THUMB_SIZES["table"] + 14)
        self.table.verticalHeader().setDefaultSectionSize(THUMB_SIZES["table"] + 10)
        self.table.itemDoubleClicked.connect(lambda _: self._open_detail())
        self.table.itemSelectionChanged.connect(self._on_selection_changed)

        self.empty = EmptyState(
            "fa5s.box-open",
            strings.INVENTORY_EMPTY,
            strings.INVENTORY_EMPTY_HINT,
            strings.INVENTORY_NEW_PRODUCT,
            self._create_product,
        )
        self.stack = QStackedWidget()
        self.stack.addWidget(self.table)
        self.stack.addWidget(self.empty)
        body.addWidget(self.stack, stretch=1)

        # Wrap the toolbar + products body in a "Produits" tab, and add a
        # second "Mouvements de stock" tab (lazy-loaded on first view).
        products_page = QWidget()
        products_layout = QVBoxLayout(products_page)
        products_layout.setContentsMargins(0, 0, 0, 0)
        products_layout.setSpacing(SPACING["md"])
        products_layout.addLayout(toolbar)
        products_layout.addLayout(body, stretch=1)

        self.movements_view = StockMovementsView(self.api, self.store_id)
        self.tabs = QTabWidget()
        self.tabs.addTab(products_page, strings.INVENTORY_TAB_PRODUCTS)
        self.tabs.addTab(self.movements_view, strings.INVENTORY_TAB_MOVEMENTS)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self.tabs, stretch=1)

        self.refresh()

    def _on_tab_changed(self, index: int) -> None:
        # Lazy-load the movements ledger the first time its tab is shown.
        if index == 1 and not self.movements_view._loaded_once:  # noqa: SLF001
            self.movements_view.refresh()

    # ------------------------------------------------------------- loading

    def refresh(self) -> None:
        run_api(
            lambda: self.api.list_categories(self.store_id),
            self._on_categories,
            lambda err: show_error(self, err.message),
        )
        run_api(
            lambda: self.api.list_products(self.store_id),
            self._on_products,
            lambda err: show_error(self, err.message),
        )

    def focus_product(self, product_id: str) -> None:
        """Select a product row (navigation from the Alertes screen)."""
        self._pending_focus = product_id
        self.search.clear()
        self.search_results = None
        if self.category_rail.count():
            self.category_rail.setCurrentRow(0)  # "Tous les produits"
        self.refresh()

    def _selected_category(self):
        """Data of the selected rail entry: None (all), a category id, or the
        '__uncategorized__' sentinel."""
        item = self.category_rail.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def _on_categories(self, categories: object) -> None:
        self.categories = list(categories)
        current = self._selected_category()
        self.category_rail.blockSignals(True)
        self.category_rail.clear()
        all_item = QListWidgetItem(strings.INVENTORY_ALL_PRODUCTS)
        all_item.setData(Qt.ItemDataRole.UserRole, None)
        self.category_rail.addItem(all_item)
        for category in self.categories:
            item = QListWidgetItem(category["name"])
            item.setData(Qt.ItemDataRole.UserRole, category["id"])
            self.category_rail.addItem(item)
        uncat = QListWidgetItem(strings.INVENTORY_UNCATEGORIZED)
        uncat.setData(Qt.ItemDataRole.UserRole, "__uncategorized__")
        self.category_rail.addItem(uncat)
        # Restore the previous selection, defaulting to "Tous".
        target = 0
        for i in range(self.category_rail.count()):
            if self.category_rail.item(i).data(Qt.ItemDataRole.UserRole) == current:
                target = i
                break
        self.category_rail.setCurrentRow(target)
        self.category_rail.blockSignals(False)
        self._render()

    def _on_products(self, products: object) -> None:
        self.products = list(products)
        self._render()
        if self._pending_focus:
            for row, product in enumerate(self.visible_products):
                if product["id"] == self._pending_focus:
                    self.table.selectRow(row)
                    self.table.scrollToItem(self.table.item(row, 1))
                    break
            self._pending_focus = None

    # ------------------------------------------------------------- search

    def _on_search_changed(self, text: str) -> None:
        if not text.strip():
            self._search_debounce.stop()
            self.search_results = None
            self._render()
            return
        self._search_debounce.start()

    def _run_search(self) -> None:
        query = self.search.text().strip()
        if not query:
            self.search_results = None
            self._render()
            return
        run_api(
            lambda: self.api.search_products(self.store_id, query=query, limit=100),
            lambda results, q=query: self._on_search_results(q, results),
            lambda err: show_error(self, err.message),
        )

    def _on_search_results(self, query: str, results: object) -> None:
        if not shiboken6.isValid(self):
            return  # screen torn down while a search was in flight
        if query != self.search.text().strip():
            return  # a newer keystroke superseded this search
        self.search_results = list(results or [])
        self._render()

    def _render(self) -> None:
        category = self._selected_category()
        names = {c["id"]: c["name"] for c in self.categories}
        base = self.search_results if self.search_results is not None else self.products

        def in_category(product: dict) -> bool:
            if category is None:
                return True
            if category == "__uncategorized__":
                return not product.get("category_id")
            return product.get("category_id") == category

        self.visible_products = [p for p in base if in_category(p)]
        self.table.set_rows(
            [
                [
                    "",  # thumbnail cell widget below
                    p["name"],
                    p.get("barcode") or "—",
                    names.get(p.get("category_id"), "—"),
                    "",  # stock cell widget below
                    fmt.fmt_money(p["price_detail"]),
                    fmt.fmt_money(p["price_gros"]),
                    fmt.fmt_money(p["price_super_gros"]),
                    strings.YES if p["is_active"] else strings.NO,
                ]
                for p in self.visible_products
            ]
        )
        for row, product in enumerate(self.visible_products):
            thumb = Thumb(THUMB_SIZES["table"])
            thumb.set_product(product)
            holder = QWidget()
            holder_layout = QHBoxLayout(holder)
            holder_layout.setContentsMargins(4, 2, 4, 2)
            holder_layout.addWidget(thumb, alignment=Qt.AlignmentFlag.AlignCenter)
            self.table.setCellWidget(row, 0, holder)

            stock_holder = QWidget()
            stock_layout = QHBoxLayout(stock_holder)
            stock_layout.setContentsMargins(4, 2, 4, 2)
            stock_layout.setSpacing(SPACING["xs"])
            stock_label = QLabel(str(product["stock_quantity"]))
            stock_layout.addWidget(stock_label)
            if product["stock_quantity"] <= product.get("low_stock_threshold", 5):
                stock_layout.addWidget(
                    Badge(strings.INVENTORY_LOW_STOCK_BADGE, "danger")
                )
            stock_layout.addStretch(1)
            self.table.setCellWidget(row, 4, stock_holder)

        empty = not self.visible_products and not self.products
        self.stack.setCurrentWidget(self.empty if empty else self.table)

    # ------------------------------------------------------------- actions

    def _on_selection_changed(self) -> None:
        has_selection = 0 <= self.table.selected_row() < len(self.visible_products)
        self.edit_button.setEnabled(has_selection)
        self.archive_button.setEnabled(has_selection)
        self.receive_button.setEnabled(has_selection)

    def _selected_product(self) -> dict | None:
        row = self.table.selected_row()
        if row < 0 or row >= len(self.visible_products):
            show_error(self, strings.INVENTORY_SELECT_ROW_FIRST)
            return None
        return self.visible_products[row]

    def _create_product(self) -> None:
        dialog = ProductDialog(self.api, self.store_id, self.categories, parent=self)
        if dialog.exec():
            self.refresh()
            if dialog.result_product:
                show_toast(
                    self,
                    strings.PRODUCT_SAVED_TOAST.format(
                        name=dialog.result_product["name"]
                    ),
                )

    def _edit_product(self) -> None:
        product = self._selected_product()
        if not product:
            return
        run_api(
            lambda: self.api.get_product_details(product["id"]),
            lambda details: self._open_edit_dialog(details),
            lambda err: show_error(self, err.message),
        )

    def _open_edit_dialog(self, details: object) -> None:
        dialog = ProductDialog(
            self.api, self.store_id, self.categories, details=details, parent=self
        )
        if dialog.exec():
            self.refresh()
            if dialog.result_product:
                show_toast(
                    self,
                    strings.PRODUCT_SAVED_TOAST.format(
                        name=dialog.result_product["name"]
                    ),
                )

    def _open_detail(self) -> None:
        product = self._selected_product()
        if not product:
            return
        ProductDetailDialog(self.api, self.store_id, product, parent=self).exec()

    def _archive_product(self) -> None:
        product = self._selected_product()
        if not product:
            return
        if not ask_confirm(
            self, strings.INVENTORY_ARCHIVE_CONFIRM.format(name=product["name"])
        ):
            return
        run_api(
            lambda: self.api.archive_product(product["id"]),
            lambda _: self.refresh(),
            lambda err: show_error(self, err.message),
        )

    def _open_label_printing(self) -> None:
        window = self.window()
        target = getattr(window, "label_printing", None)
        if target is not None and hasattr(window, "navigate"):
            window.navigate(target)

    def _adjust_stock(self) -> None:
        dialog = StockAdjustDialog(self.api, self.store_id, parent=self)
        if not dialog.exec() or not dialog.result:
            return
        result = dialog.result
        self.refresh()  # product stock changed
        # Keep the movements ledger in sync if the operator has opened it.
        if self.movements_view._loaded_once:  # noqa: SLF001
            self.movements_view.refresh()
        show_toast(
            self,
            strings.ADJUST_DONE_TOAST.format(
                product=result["name"],
                old=result["old_quantity"],
                new=result["new_quantity"],
            ),
        )

    def _receive_stock(self) -> None:
        product = self._selected_product()
        if not product:
            return
        qty, ok = QInputDialog.getInt(
            self,
            "Réceptionner",
            f"Quantité à ajouter pour {product['name']} :",
            1,
            1,
            1000000,
        )
        if ok and qty > 0:
            # We fetch details first to get the full payload
            run_api(
                lambda: self.api.get_product_details(product["id"]),
                lambda details: self._do_receive_stock(details, qty),
                lambda err: show_error(self, err.message),
            )

    def _do_receive_stock(self, details: dict, added_qty: int) -> None:
        details["stock_quantity"] += added_qty
        run_api(
            lambda: self.api.update_product(details["id"], details),
            lambda _: self._on_receive_done(added_qty, details["name"]),
            lambda err: show_error(self, err.message),
        )

    def _on_receive_done(self, qty: int, name: str) -> None:
        self.refresh()
        show_toast(self, f"{qty} unités ajoutées à {name}.")

    def _import_csv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, strings.IMPORT_BUTTON, "", strings.IMPORT_FILE_FILTER
        )
        if not path:
            return
        data = Path(path).read_bytes()
        run_api(
            lambda: self.api.import_products_csv(self.store_id, data),
            self._on_import_done,
            lambda err: show_error(self, err.message),
        )

    def _on_import_done(self, result: object) -> None:
        created = result.get("created", 0)
        updated = result.get("updated", 0)
        errors = result.get("errors", [])
        show_toast(
            self,
            strings.IMPORT_DONE_TOAST.format(created=created, updated=updated),
        )
        if errors:
            from ui.widgets.data_table import DataTable
            from ui.widgets.modal import ModalDialog

            dlg = ModalDialog(strings.IMPORT_DIALOG_TITLE, self)
            summary = QLabel(
                f"{strings.IMPORT_CREATED.format(count=created)}  ·  "
                f"{strings.IMPORT_UPDATED.format(count=updated)}  ·  "
                f"{strings.IMPORT_ERRORS.format(count=len(errors))}"
            )
            dlg.content.addWidget(summary)
            table = DataTable([strings.IMPORT_COL_ROW, strings.IMPORT_COL_ERROR])
            table.set_rows([[str(e["row"]), e["message"]] for e in errors])
            table.setMinimumHeight(200)
            dlg.content.addWidget(table)
            dlg.exec()
        self.refresh()
