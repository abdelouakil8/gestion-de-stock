"""Store-wide stock movements log — a filterable ledger embedded as a tab of
the Inventory screen.

Server-side filters: date range, category and movement type (the backend
joins the product name/barcode/category in, so there is no N+1 lookup here).
A product text box refines the loaded page client-side. Rows can be exported
to XLSX (generated client-side with openpyxl — no export endpoint needed).
"""

import qtawesome as qta
import shiboken6
from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from services.workers import run_api
from ui import format as fmt
from ui import strings
from ui.styles.tokens import ICON_SIZES, NEUTRAL, SEMANTIC, SPACING
from ui.widgets.badge import Badge
from ui.widgets.data_table import DataTable
from ui.widgets.modal import show_error
from ui.widgets.states import EmptyState, StatefulStack
from ui.widgets.toast import show_toast

_TYPE_LABELS = {
    "sale": strings.MOVEMENT_TYPE_SALE,
    "purchase": strings.MOVEMENT_TYPE_PURCHASE,
    "refund": strings.MOVEMENT_TYPE_REFUND,
    "adjustment": strings.MOVEMENT_TYPE_ADJUSTMENT,
}
_TYPE_KIND = {
    "sale": "danger",
    "purchase": "success",
    "refund": "warning",
    "adjustment": "accent",
}
# Filter option -> server movement_type code (None = every type).
_TYPE_FILTERS = [
    ("", strings.MOVEMENTS_FILTER_ALL_TYPES),
    ("sale", strings.MOVEMENTS_FILTER_SALES),
    ("purchase", strings.MOVEMENTS_FILTER_PURCHASES),
    ("adjustment", strings.MOVEMENTS_FILTER_ADJUSTMENTS),
    ("refund", strings.MOVEMENTS_FILTER_RETURNS),
]
_PAGE = 200


class StockMovementsView(QWidget):
    def __init__(self, api, store_id: str, parent=None) -> None:
        super().__init__(parent)
        self.api = api
        self.store_id = store_id
        self.movements: list[dict] = []
        self._loaded_once = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACING["md"])

        # ------------------------------------------------------- filters
        filters = QHBoxLayout()
        filters.setSpacing(SPACING["sm"])

        filters.addWidget(QLabel(strings.MOVEMENTS_FROM))
        self.date_from = QDateEdit(QDate.currentDate().addDays(-29))
        self.date_from.setCalendarPopup(True)
        self.date_from.setDisplayFormat("dd/MM/yyyy")
        self.date_from.dateChanged.connect(lambda _: self.refresh())
        filters.addWidget(self.date_from)

        filters.addWidget(QLabel(strings.MOVEMENTS_TO))
        self.date_to = QDateEdit(QDate.currentDate())
        self.date_to.setCalendarPopup(True)
        self.date_to.setDisplayFormat("dd/MM/yyyy")
        self.date_to.dateChanged.connect(lambda _: self.refresh())
        filters.addWidget(self.date_to)

        self.category_combo = QComboBox()
        self.category_combo.addItem(strings.MOVEMENTS_FILTER_ALL_CATEGORIES, None)
        self.category_combo.currentIndexChanged.connect(lambda _: self.refresh())
        filters.addWidget(self.category_combo)

        self.type_combo = QComboBox()
        for code, label in _TYPE_FILTERS:
            self.type_combo.addItem(label, code)
        self.type_combo.currentIndexChanged.connect(lambda _: self.refresh())
        filters.addWidget(self.type_combo)

        self.product_filter = QLineEdit()
        self.product_filter.setObjectName("SearchInput")
        self.product_filter.setPlaceholderText(strings.MOVEMENTS_SEARCH_PLACEHOLDER)
        self.product_filter.textChanged.connect(lambda _: self._render())
        filters.addWidget(self.product_filter, stretch=1)

        self.export_button = QPushButton(
            qta.icon("fa5s.file-excel", color=NEUTRAL["600"]),
            strings.MOVEMENTS_EXPORT_XLSX,
        )
        self.export_button.clicked.connect(self._export_xlsx)
        filters.addWidget(self.export_button)
        layout.addLayout(filters)

        # --------------------------------------------------------- table
        self.table = DataTable(
            [
                strings.MOVEMENTS_COL_DATETIME,
                strings.MOVEMENTS_COL_PRODUCT,
                strings.MOVEMENTS_COL_CATEGORY,
                strings.MOVEMENTS_COL_TYPE,
                strings.MOVEMENTS_COL_DELTA,
                strings.MOVEMENTS_COL_AFTER,
                strings.MOVEMENTS_COL_REFERENCE,
                strings.MOVEMENTS_COL_NOTE,
            ]
        )
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        self.stack = StatefulStack(
            self.table,
            EmptyState("fa5s.exchange-alt", strings.MOVEMENTS_EMPTY),
        )
        layout.addWidget(self.stack, stretch=1)
        
        from ui.widgets.pagination import PaginationBar
        self.pagination = PaginationBar()
        self.pagination.page_changed.connect(self._load_page)
        layout.addWidget(self.pagination)

        self._page = 0
        self._page_size = _PAGE

    # ------------------------------------------------------------- loading

    def _ensure_categories(self) -> None:
        if self.category_combo.count() > 1:
            return
        run_api(
            lambda: self.api.list_categories(self.store_id),
            self._on_categories,
            lambda err: None,  # category filter is optional
        )

    def _on_categories(self, categories: object) -> None:
        if not shiboken6.isValid(self):
            return
        for category in categories:
            self.category_combo.addItem(category["name"], category["id"])

    def _load_page(self, page: int) -> None:
        self._page = page
        offset = page * self._page_size
        self._loaded_once = True
        self._ensure_categories()
        self.stack.show_loading()
        date_from = self.date_from.date().toString("yyyy-MM-dd") + "T00:00:00"
        # Exclusive upper bound: include the whole selected end day.
        date_to = self.date_to.date().addDays(1).toString("yyyy-MM-dd") + "T00:00:00"
        run_api(
            lambda: self.api.list_stock_movements(
                self.store_id,
                category_id=self.category_combo.currentData(),
                type=self.type_combo.currentData() or None,
                date_from=date_from,
                date_to=date_to,
                limit=self._page_size,
                offset=offset,
            ),
            self._on_loaded,
            self._on_error,
        )

    def refresh(self) -> None:
        """Reload the ledger from the server with the current filters."""
        self._load_page(0)

    def _on_loaded(self, page: object) -> None:
        if not shiboken6.isValid(self):
            return
        self.movements = page.get("items", []) if isinstance(page, dict) else []
        total = page.get("total", 0) if isinstance(page, dict) else 0
        import math
        total_pages = max(1, math.ceil(total / self._page_size))
        self.pagination.set_state(self._page, total_pages)
        self._render()

    def _on_error(self, err) -> None:
        if not shiboken6.isValid(self):
            return
        self.stack.show_empty()
        if err.code in ("invalid_pin", "pin_not_configured"):
            show_error(self, strings.PIN_REQUIRED_ACTION)
        else:
            show_error(self, err.message)

    # ------------------------------------------------------------- render

    def _visible(self) -> list[dict]:
        query = self.product_filter.text().strip().casefold()
        if not query:
            return self.movements
        return [
            mv
            for mv in self.movements
            if query in (mv.get("product_name") or "").casefold()
            or query in (mv.get("product_barcode") or "").casefold()
        ]

    def _render(self) -> None:
        rows = self._visible()
        if not rows:
            self.stack.show_empty()
            return
        self.table.set_rows(
            [
                [
                    fmt.fmt_datetime(mv.get("created_at")),
                    self._product_text(mv),
                    mv.get("category_name") or "—",
                    "",  # type cell widget below
                    "",  # delta cell widget below
                    self._stock_text(mv),
                    self._reference_text(mv),
                    mv.get("note") or "—",
                ]
                for mv in rows
            ]
        )
        for row, mv in enumerate(rows):
            self.table.setCellWidget(row, 3, self._type_cell(mv))
            self.table.setCellWidget(row, 4, self._delta_cell(mv))
        self.stack.show_content()

    @staticmethod
    def _product_text(mv: dict) -> str:
        name = mv.get("product_name") or "—"
        barcode = mv.get("product_barcode")
        return f"{name}\n{barcode}" if barcode else name

    @staticmethod
    def _stock_text(mv: dict) -> str:
        after = mv.get("quantity_after")
        delta = mv.get("quantity_delta", 0) or 0
        if after is None:
            return "—"
        before = after - delta
        return f"{before} → {after}"

    @staticmethod
    def _reference_text(mv: dict) -> str:
        ref = mv.get("reference_id")
        return str(ref)[:8].upper() if ref else "—"

    def _type_cell(self, mv: dict) -> QWidget:
        mtype = mv.get("movement_type", "")
        delta = int(mv.get("quantity_delta", 0) or 0)
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(SPACING["xs"], 2, SPACING["xs"], 2)
        row.setSpacing(SPACING["xs"])
        up = delta >= 0
        color = SEMANTIC["success"] if up else SEMANTIC["danger"]
        arrow = QLabel()
        arrow.setPixmap(
            qta.icon("fa5s.arrow-up" if up else "fa5s.arrow-down", color=color).pixmap(
                ICON_SIZES["sm"], ICON_SIZES["sm"]
            )
        )
        arrow.setStyleSheet("background: transparent;")
        row.addWidget(arrow)
        row.addWidget(
            Badge(_TYPE_LABELS.get(mtype, mtype), _TYPE_KIND.get(mtype, "neutral"))
        )
        row.addStretch(1)
        return holder

    def _delta_cell(self, mv: dict) -> QWidget:
        delta = int(mv.get("quantity_delta", 0) or 0)
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(SPACING["xs"], 2, SPACING["xs"], 2)
        if delta > 0:
            text, color = f"+{delta}", SEMANTIC["success"]
        elif delta < 0:
            text, color = f"−{abs(delta)}", SEMANTIC["danger"]
        else:
            text, color = "0", NEUTRAL["500"]
        label = QLabel(text)
        label.setStyleSheet(
            f"color: {color}; font-weight: 700; background: transparent;"
        )
        label.setAlignment(Qt.AlignmentFlag.AlignTrailing | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(label)
        return holder

    # ------------------------------------------------------------- export

    def _export_xlsx(self) -> None:
        rows = self._visible()
        if not rows:
            show_toast(self, strings.MOVEMENTS_EXPORT_EMPTY, kind="warning")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, strings.MOVEMENTS_EXPORT_XLSX, "mouvements.xlsx", "Excel (*.xlsx)"
        )
        if not path:
            return
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Font

            wb = Workbook()
            ws = wb.active
            ws.title = strings.INVENTORY_TAB_MOVEMENTS[:31]
            headers = [
                strings.MOVEMENTS_COL_DATETIME,
                strings.MOVEMENTS_COL_PRODUCT,
                "Code-barres",
                strings.MOVEMENTS_COL_CATEGORY,
                strings.MOVEMENTS_COL_TYPE,
                strings.MOVEMENTS_COL_DELTA,
                strings.MOVEMENTS_COL_AFTER,
                strings.MOVEMENTS_COL_REFERENCE,
                strings.MOVEMENTS_COL_NOTE,
            ]
            ws.append(headers)
            for cell in ws[1]:
                cell.font = Font(bold=True)
            for mv in rows:
                ws.append(
                    [
                        fmt.fmt_datetime(mv.get("created_at")),
                        mv.get("product_name") or "",
                        mv.get("product_barcode") or "",
                        mv.get("category_name") or "",
                        _TYPE_LABELS.get(
                            mv.get("movement_type"), mv.get("movement_type") or ""
                        ),
                        int(mv.get("quantity_delta", 0) or 0),
                        mv.get("quantity_after"),
                        self._reference_text(mv),
                        mv.get("note") or "",
                    ]
                )
            widths = (16, 30, 16, 18, 14, 10, 12, 12, 30)
            for column, width in zip("ABCDEFGHI", widths, strict=True):
                ws.column_dimensions[column].width = width
            wb.save(path)
            show_toast(self, strings.EXPORT_SAVED_TOAST.format(path=path))
        except (OSError, ImportError) as exc:
            show_error(self, str(exc))
