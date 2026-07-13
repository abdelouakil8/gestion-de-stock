"""Product create/edit form and packaging row widget."""

from pathlib import Path

import qtawesome as qta
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from services import image_cache
from services.workers import run_api
from ui import strings
from ui.styles.tokens import NEUTRAL, SPACING, THUMB_SIZES
from ui.widgets.modal import ModalDialog, show_error
from ui.widgets.thumb import Thumb

_CONTENT_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}

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
    """Create/edit product form. `details` present => edit mode (owner data).

    Price-level ordering (detail >= gros >= super gros) is hinted LIVE here
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

        packaging_title = QLabel(strings.PRODUCT_PACKAGINGS)
        packaging_title.setObjectName("SectionTitle")
        self.content.addWidget(packaging_title)
        packaging_hint = QLabel(strings.PACKAGING_HINT)
        packaging_hint.setObjectName("FieldHint")
        packaging_hint.setWordWrap(True)
        self.content.addWidget(packaging_hint)
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
            from ui.widgets.modal import show_error as _show_error

            _show_error(self, strings.ERROR_TITLE, f"Erreur d'impression : {e}")

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
        index = self.category_combo.count() - 1
        self.category_combo.insertItem(index, category["name"], category["id"])
        self.category_combo.setCurrentIndex(index)

    def _on_category_error(self, err) -> None:
        self.category_combo.setEnabled(True)
        self.category_combo.setCurrentIndex(0)
        show_error(self, err.message)

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

    def accept(self) -> None:
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
        super().accept()

    def _on_save_error(self, err) -> None:
        self.ok_button.setEnabled(True)
        show_error(self, err.message)
