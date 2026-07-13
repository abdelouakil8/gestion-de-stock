"""Product detail dialog — read-only sheet with stats and movement ledger."""

from decimal import Decimal

import qtawesome as qta
import shiboken6
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from services.workers import run_api
from ui import format as fmt
from ui import strings
from ui.styles.tokens import ICON_SIZES, SEMANTIC, SPACING, THUMB_SIZES
from ui.widgets.badge import Badge
from ui.widgets.bars import BarChart
from ui.widgets.modal import ModalDialog
from ui.widgets.states import EmptyState, StatefulStack
from ui.widgets.thumb import Thumb


def _movement_type_label(key: str) -> str:
    return {
        "sale": strings.MOVEMENT_TYPE_SALE,
        "purchase": strings.MOVEMENT_TYPE_PURCHASE,
        "refund": strings.MOVEMENT_TYPE_REFUND,
        "adjustment": strings.MOVEMENT_TYPE_ADJUSTMENT,
    }.get(key, key)


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
            text = f"−{abs(delta)}"
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

        run_api(
            lambda: self.api.stats_product(store_id, product["id"]),
            self._on_stats,
            self._on_stats_error,
        )

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
