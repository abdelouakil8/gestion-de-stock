"""Impression d'étiquettes — barcode label sheets.

Left: pick products (a filterable, checkable list showing current stock, plus
select-all / none). Right: label options (size, copies, what to show, price
level, barcode symbology) with a live QPainter preview. "Imprimer" sends the
generated PDF to the configured label printer; "Exporter PDF" opens it.

The PDF itself (with real barcodes) is generated server-side; the preview is a
lightweight mock. All network goes through run_api.
"""

import tempfile
from pathlib import Path

import qtawesome as qta
import shiboken6
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QProgressDialog,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from services import printing
from services.workers import run_api
from ui import format as fmt
from ui import strings
from ui.styles.tokens import NEUTRAL, SPACING
from ui.widgets.card import SectionCard
from ui.widgets.modal import show_error
from ui.widgets.toast import show_toast

_SIZES = [("58x30", "58 × 30 mm"), ("58x40", "58 × 40 mm"), ("40x25", "40 × 25 mm")]
_SIZE_DIMS = {"58x30": (58, 30), "58x40": (58, 40), "40x25": (40, 25)}


class LabelPreview(QWidget):
    """A lightweight painted mock of one label reacting to the config."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(180)
        self._config: dict = {}
        self._product: dict | None = None

    def set_state(self, config: dict, product: dict | None) -> None:
        self._config = config
        self._product = product
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w_mm, h_mm = _SIZE_DIMS.get(self._config.get("size", "58x30"), (58, 30))
        # Fit the label into the widget preserving aspect ratio.
        scale = min((self.width() - 20) / w_mm, (self.height() - 20) / h_mm, 6.0)
        lw, lh = w_mm * scale, h_mm * scale
        x = (self.width() - lw) / 2
        y = (self.height() - lh) / 2
        painter.setPen(QColor(NEUTRAL["400"]))
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawRect(QRectF(x, y, lw, lh))

        painter.setPen(QColor(NEUTRAL["800"]))
        cursor = y + 10
        product = self._product or {"name": "Produit", "barcode": "000000000000"}
        if self._config.get("show_store") and self._config.get("store_name"):
            painter.setFont(QFont("Helvetica", 6))
            painter.drawText(
                QRectF(x, cursor, lw, 12),
                Qt.AlignmentFlag.AlignHCenter,
                str(self._config["store_name"])[:30],
            )
            cursor += 12
        if self._config.get("show_name", True):
            f = QFont("Helvetica")
            f.setBold(True)
            f.setPointSize(9)
            painter.setFont(f)
            painter.drawText(
                QRectF(x, cursor, lw, 16),
                Qt.AlignmentFlag.AlignHCenter,
                str(product.get("name", ""))[:24],
            )
            cursor += 16
        if self._config.get("show_price", True):
            field = {
                "detail": "price_detail",
                "gros": "price_gros",
                "super_gros": "price_super_gros",
            }.get(self._config.get("price_level", "detail"), "price_detail")
            f = QFont("Helvetica")
            f.setBold(True)
            f.setPointSize(11)
            painter.setFont(f)
            painter.drawText(
                QRectF(x, cursor, lw, 18),
                Qt.AlignmentFlag.AlignHCenter,
                fmt.fmt_money(product.get(field, 0)),
            )
            cursor += 18
        if self._config.get("show_barcode", True):
            # Mock barcode: a band of vertical bars + the code text.
            band_h = min(24, y + lh - cursor - 14)
            if band_h > 6:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(NEUTRAL["800"]))
                bx = x + 12
                import_i = 0
                widths = [1, 2, 1, 3, 1, 1, 2, 1, 2, 3, 1, 2, 1, 1, 3, 1, 2, 1]
                while bx < x + lw - 12 and import_i < 400:
                    bw = widths[import_i % len(widths)] * max(1.0, scale / 3)
                    painter.drawRect(QRectF(bx, cursor, bw, band_h))
                    bx += bw + max(1.0, scale / 3)
                    import_i += 1
                painter.setPen(QColor(NEUTRAL["700"]))
                painter.setFont(QFont("Helvetica", 6))
                painter.drawText(
                    QRectF(x, cursor + band_h, lw, 12),
                    Qt.AlignmentFlag.AlignHCenter,
                    str(product.get("barcode") or ""),
                )
        painter.end()


class LabelPrintingScreen(QWidget):
    def __init__(self, api, store_id: str, parent=None) -> None:
        super().__init__(parent)
        self.api = api
        self.store_id = store_id
        self.products: list[dict] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(*[SPACING["xl"]] * 4)
        outer.setSpacing(SPACING["md"])

        header = QHBoxLayout()
        title = QLabel(strings.LABELS_TITLE)
        title.setObjectName("ScreenTitle")
        header.addWidget(title)
        header.addStretch(1)
        refresh = QPushButton(
            qta.icon("fa5s.sync", color=NEUTRAL["600"]), strings.REFRESH
        )
        refresh.clicked.connect(self.refresh)
        header.addWidget(refresh)
        outer.addLayout(header)

        body = QHBoxLayout()
        body.setSpacing(SPACING["lg"])
        body.addWidget(self._build_selection(), stretch=2)
        body.addWidget(self._build_config(), stretch=1)
        outer.addLayout(body, stretch=1)

    # --------------------------------------------------------------- build

    def _build_selection(self) -> QWidget:
        card = SectionCard(strings.LABELS_SELECT_PRODUCTS, "fa5s.boxes")
        self.filter_input = QLineEdit()
        self.filter_input.setObjectName("SearchInput")
        self.filter_input.setPlaceholderText(strings.SEARCH)
        self.filter_input.textChanged.connect(self._apply_filter)
        card.body.addWidget(self.filter_input)

        self.list = QListWidget()
        self.list.itemChanged.connect(lambda _: self._update_count())
        card.body.addWidget(self.list, stretch=1)

        buttons = QHBoxLayout()
        select_all = QPushButton(strings.LABELS_SELECT_ALL)
        select_all.setObjectName("Secondary")
        select_all.clicked.connect(lambda: self._set_all(True))
        clear_all = QPushButton(strings.LABELS_SELECT_NONE)
        clear_all.setObjectName("Secondary")
        clear_all.clicked.connect(lambda: self._set_all(False))
        self.count_label = QLabel("")
        self.count_label.setObjectName("Muted")
        buttons.addWidget(select_all)
        buttons.addWidget(clear_all)
        buttons.addStretch(1)
        buttons.addWidget(self.count_label)
        card.body.addLayout(buttons)
        return card

    def _build_config(self) -> QWidget:
        card = SectionCard(strings.LABELS_CONFIG, "fa5s.sliders-h")

        card.body.addWidget(QLabel(strings.LABELS_SIZE))
        self.size_combo = QComboBox()
        for value, label in _SIZES:
            self.size_combo.addItem(label, value)
        self.size_combo.currentIndexChanged.connect(self._sync_preview)
        card.body.addWidget(self.size_combo)

        copies_row = QHBoxLayout()
        copies_row.addWidget(QLabel(strings.LABELS_COPIES))
        self.copies_input = QSpinBox()
        self.copies_input.setRange(1, 999)
        copies_row.addWidget(self.copies_input)
        copies_row.addStretch(1)
        card.body.addLayout(copies_row)

        self.show_name = QCheckBox(strings.LABELS_SHOW_NAME)
        self.show_name.setChecked(True)
        self.show_price = QCheckBox(strings.LABELS_SHOW_PRICE)
        self.show_price.setChecked(True)
        self.show_barcode = QCheckBox(strings.LABELS_SHOW_BARCODE)
        self.show_barcode.setChecked(True)
        self.show_store = QCheckBox(strings.LABELS_SHOW_STORE)
        for check in (
            self.show_name,
            self.show_price,
            self.show_barcode,
            self.show_store,
        ):
            check.toggled.connect(self._sync_preview)
            card.body.addWidget(check)

        card.body.addWidget(QLabel(strings.LABELS_PRICE_LEVEL))
        self.price_level_combo = QComboBox()
        for value in ("detail", "gros", "super_gros"):
            self.price_level_combo.addItem(strings.PRICE_LEVEL_LABELS[value], value)
        self.price_level_combo.currentIndexChanged.connect(self._sync_preview)
        card.body.addWidget(self.price_level_combo)

        card.body.addWidget(QLabel(strings.LABELS_BARCODE_TYPE))
        self.barcode_type_combo = QComboBox()
        self.barcode_type_combo.addItem("Code128", "code128")
        self.barcode_type_combo.addItem("EAN-13", "ean13")
        self.barcode_type_combo.currentIndexChanged.connect(self._sync_preview)
        card.body.addWidget(self.barcode_type_combo)

        card.body.addWidget(QLabel(strings.LABELS_PREVIEW))
        self.preview = LabelPreview()
        card.body.addWidget(self.preview)

        actions = QHBoxLayout()
        print_button = QPushButton(
            qta.icon("fa5s.print", color="white"), strings.LABELS_PRINT
        )
        print_button.setObjectName("Primary")
        print_button.clicked.connect(lambda: self._generate(print_after=True))
        export_button = QPushButton(
            qta.icon("fa5s.file-pdf", color=NEUTRAL["600"]), strings.LABELS_EXPORT
        )
        export_button.setObjectName("Secondary")
        export_button.clicked.connect(lambda: self._generate(print_after=False))
        actions.addWidget(print_button)
        actions.addWidget(export_button)
        card.body.addLayout(actions)
        card.body.addStretch(1)
        return card

    # ------------------------------------------------------------- loading

    def refresh(self) -> None:
        run_api(
            lambda: self.api.list_products(self.store_id),
            self._on_products,
            lambda err: show_error(self, err.message),
        )

    def _on_products(self, products: object) -> None:
        if not shiboken6.isValid(self):
            return
        self.products = list(products or [])
        self.list.blockSignals(True)
        self.list.clear()
        for product in self.products:
            item = QListWidgetItem(
                strings.LABELS_PRODUCT_ROW.format(
                    name=product["name"], stock=product["stock_quantity"]
                )
            )
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, product)
            self.list.addItem(item)
        self.list.blockSignals(False)
        self._update_count()
        self._sync_preview()

    def _apply_filter(self, text: str) -> None:
        query = text.strip().casefold()
        for i in range(self.list.count()):
            item = self.list.item(i)
            product = item.data(Qt.ItemDataRole.UserRole)
            name = (product.get("name") or "").casefold()
            barcode = (product.get("barcode") or "").casefold()
            item.setHidden(bool(query) and query not in name and query not in barcode)

    def _set_all(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        self.list.blockSignals(True)
        for i in range(self.list.count()):
            item = self.list.item(i)
            if not item.isHidden():
                item.setCheckState(state)
        self.list.blockSignals(False)
        self._update_count()

    def _checked_products(self) -> list[dict]:
        result = []
        for i in range(self.list.count()):
            item = self.list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                result.append(item.data(Qt.ItemDataRole.UserRole))
        return result

    def _update_count(self) -> None:
        count = len(self._checked_products())
        self.count_label.setText(strings.LABELS_SELECTED_COUNT.format(n=count))
        self._sync_preview()

    def _config(self) -> dict:
        return {
            "size": self.size_combo.currentData(),
            "copies": self.copies_input.value(),
            "show_name": self.show_name.isChecked(),
            "show_price": self.show_price.isChecked(),
            "show_barcode": self.show_barcode.isChecked(),
            "show_store": self.show_store.isChecked(),
            "price_level": self.price_level_combo.currentData(),
            "barcode_type": self.barcode_type_combo.currentData(),
        }

    def _sync_preview(self) -> None:
        config = self._config()
        config["store_name"] = getattr(self.window(), "store", {}).get("name", "")
        checked = self._checked_products()
        self.preview.set_state(config, checked[0] if checked else None)

    # ------------------------------------------------------------- generate

    def _generate(self, print_after: bool) -> None:
        products = self._checked_products()
        if not products:
            show_error(self, strings.LABELS_NONE_SELECTED)
            return
        product_ids = [p["id"] for p in products]
        config = self._config()
        config.pop("store_name", None)

        progress = QProgressDialog(strings.LABELS_GENERATING, "", 0, 0, self)
        progress.setCancelButton(None)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.show()

        run_api(
            lambda: self.api.generate_labels(self.store_id, product_ids, config),
            lambda pdf: self._on_pdf(progress, pdf, print_after),
            lambda err: self._on_error(progress, err),
        )

    def _on_pdf(self, progress, pdf: object, print_after: bool) -> None:
        progress.close()
        if not shiboken6.isValid(self):
            return
        path = Path(tempfile.gettempdir()) / "etiquettes.pdf"
        try:
            path.write_bytes(pdf)
        except OSError as exc:
            show_error(self, strings.OPEN_PDF_FAILED.format(path=exc))
            return
        if print_after:
            printing.print_pdf(path, printing.get_selected_printer())
            show_toast(self, strings.LABELS_SENT_TO_PRINTER)
        else:
            printing.open_file(path)

    def _on_error(self, progress, err) -> None:
        progress.close()
        if shiboken6.isValid(self):
            show_error(self, err.message)
