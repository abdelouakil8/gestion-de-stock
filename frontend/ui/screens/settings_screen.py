"""Réglages — receipt customization with live preview, language, accent.

The receipt preview is a faithful local mock of the backend's 80mm layout
(services/receipts.py): header (shop name / phone / address), sample line,
total, the credit block when enabled, footer. It re-renders on every
keystroke. Saving goes through PUT /settings (PIN-gated server-side); a
saved accent color re-applies the stylesheet live, no restart.
"""

from datetime import datetime
from functools import partial

import qtawesome as qta
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from services import printing
from services.workers import run_api
from ui import strings
from ui.styles.tokens import ACCENT_PRESETS, NEUTRAL, SPACING, render_qss
from ui.widgets.card import SectionCard
from ui.widgets.modal import ModalDialog, show_error, show_info
from ui.widgets.toast import show_toast


class FactoryResetDialog(ModalDialog):
    """Type-your-PIN confirmation for the full wipe. The typed PIN is sent
    to the server, which is the only judge — no cached credential reuse."""

    def __init__(self, api, parent=None) -> None:
        super().__init__(strings.RESET_DIALOG_TITLE, parent)
        self.api = api
        # NB: never name this "done" — it would shadow QDialog.done(),
        # which accept() invokes virtually (hard crash).
        self.reset_done = False

        warning = QLabel(strings.RESET_DIALOG_WARNING)
        warning.setObjectName("FieldError")
        warning.setWordWrap(True)
        self.content.addWidget(warning)

        self.content.addWidget(QLabel(strings.RESET_DIALOG_PIN_PROMPT))
        self.pin_input = QLineEdit()
        self.pin_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pin_input.textChanged.connect(
            lambda text: self.ok_button.setEnabled(bool(text.strip()))
        )
        self.content.addWidget(self.pin_input)

        self.ok_button.setText(strings.RESET_DIALOG_CONFIRM)
        self.ok_button.setObjectName("Danger")
        self.ok_button.setEnabled(False)
        self.pin_input.setFocus()

    def accept(self) -> None:
        pin = self.pin_input.text().strip()
        if not pin:
            return
        self.ok_button.setEnabled(False)
        run_api(
            lambda: self.api.factory_reset(pin),
            self._on_done,
            self._on_error,
        )

    def _on_done(self, _result: object) -> None:
        self.reset_done = True
        super().accept()

    def _on_error(self, err) -> None:
        self.ok_button.setEnabled(True)
        show_error(self, err.message)
        self.pin_input.selectAll()
        self.pin_input.setFocus()


class ReceiptPreview(QFrame):
    """Local mock of the printed receipt — same information layout.

    Rendered as ONE monospace label rebuilt from scratch on every change:
    no widget churn, so nothing can ever overlap or leak between renders.
    """

    COLS = 32  # characters per 80mm-style line

    def __init__(self, store_name: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("ReceiptPaper")
        self.store_name = store_name
        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            SPACING["lg"], SPACING["lg"], SPACING["lg"], SPACING["lg"]
        )
        self._label = QLabel("")
        self._label.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self._label)

    def render_preview(
        self,
        shop_name: str,
        phone: str,
        address: str,
        footer: str,
        show_credit: bool,
    ) -> None:
        width = self.COLS

        def fit(text: str) -> str:
            return text if len(text) <= width else text[: width - 1] + "…"

        def center(text: str) -> str:
            return fit(text).center(width).rstrip()

        def row(left: str, right: str) -> str:
            space = width - len(right)
            return fit(left)[:space].ljust(space) + right

        lines = [center(shop_name or self.store_name)]
        if phone:
            lines.append(center(f"Tél : {phone}"))
        if address:
            lines.append(center(address))
        lines.append(center(datetime.now().strftime("Le %d/%m/%Y %H:%M")))
        lines.append(center(strings.SETTINGS_PREVIEW_TICKET))
        lines.append("-" * width)
        lines.append(fit(strings.SETTINGS_PREVIEW_SAMPLE_PRODUCT))
        lines.append(row("  2 x 40.00", "80.00"))
        lines.append("-" * width)
        lines.append(row(strings.SETTINGS_PREVIEW_TOTAL, "80.00"))
        if show_credit:
            lines.append(fit(strings.SETTINGS_PREVIEW_CUSTOMER))
            lines.append(row(strings.SETTINGS_PREVIEW_PAID, "30.00"))
            lines.append(row(strings.SETTINGS_PREVIEW_REMAINING, "50.00"))
        lines.append("")
        lines.append(center(footer or strings.SETTINGS_PREVIEW_DEFAULT_FOOTER))
        self._label.setText("\n".join(lines))


class SettingsScreen(QWidget):
    def __init__(self, api, store: dict, parent=None) -> None:
        super().__init__(parent)
        self.api = api
        self.store_id = store["id"]
        self.store_name = store.get("name", "")
        self.settings: dict = {}
        self._accent = None  # currently chosen (unsaved) accent

        outer = QVBoxLayout(self)
        outer.setContentsMargins(*[SPACING["xl"]] * 4)
        outer.setSpacing(SPACING["md"])

        header = QHBoxLayout()
        title = QLabel(strings.SETTINGS_TITLE)
        title.setObjectName("ScreenTitle")
        header.addWidget(title)
        header.addStretch(1)
        self.save_button = QPushButton(
            qta.icon("fa5s.check", color="white"), strings.SAVE
        )
        self.save_button.setObjectName("Primary")
        self.save_button.clicked.connect(self._save)
        header.addWidget(self.save_button)
        outer.addLayout(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        body = QHBoxLayout(content)
        body.setSpacing(SPACING["lg"])

        left = QVBoxLayout()
        left.setSpacing(SPACING["md"])

        # ------------------------------------------------ receipt fields
        receipt_card = SectionCard(strings.SETTINGS_RECEIPT_SECTION, "fa5s.receipt")
        form = QFormLayout()
        form.setSpacing(SPACING["md"])
        self.shop_name_input = QLineEdit()
        self.phone_input = QLineEdit()
        self.address_input = QLineEdit()
        self.footer_input = QLineEdit()
        self.credit_check = QCheckBox(strings.SETTINGS_SHOW_CREDIT)
        form.addRow(strings.SETTINGS_SHOP_NAME, self.shop_name_input)
        form.addRow(strings.SETTINGS_PHONE, self.phone_input)
        form.addRow(strings.SETTINGS_ADDRESS, self.address_input)
        form.addRow(strings.SETTINGS_FOOTER, self.footer_input)
        form.addRow("", self.credit_check)
        receipt_card.body.addLayout(form)
        left.addWidget(receipt_card)

        for field in (
            self.shop_name_input,
            self.phone_input,
            self.address_input,
            self.footer_input,
        ):
            field.textChanged.connect(self._update_preview)
        self.credit_check.toggled.connect(self._update_preview)

        # ---------------------------------------------------- language
        language_card = SectionCard(strings.SETTINGS_LANGUAGE_SECTION, "fa5s.language")
        self.language_combo = QComboBox()
        self.language_combo.addItem(strings.SETTINGS_LANGUAGE_FR, "fr")
        self.language_combo.addItem(strings.SETTINGS_LANGUAGE_AR, "ar")
        # Arabic is listed but not shipped yet — visibly disabled with the
        # "à venir" mention rather than silently failing.
        model_item = self.language_combo.model().item(1)
        model_item.setEnabled(False)
        language_card.body.addWidget(self.language_combo)
        left.addWidget(language_card)

        # ------------------------------------------------------ printer
        printer_card = SectionCard(strings.SETTINGS_PRINTER_SECTION, "fa5s.print")
        printer_hint = QLabel(strings.SETTINGS_PRINTER_HINT)
        printer_hint.setObjectName("FieldHint")
        printer_hint.setWordWrap(True)
        printer_card.body.addWidget(printer_hint)
        self.printer_combo = QComboBox()
        self.printer_combo.addItem(strings.SETTINGS_PRINTER_DEFAULT, None)
        for name in printing.available_printers():
            self.printer_combo.addItem(name, name)
        current_printer = printing.get_selected_printer()
        if current_printer:
            index = self.printer_combo.findData(current_printer)
            self.printer_combo.setCurrentIndex(max(index, 0))
        self.printer_combo.currentIndexChanged.connect(self._on_printer_changed)
        printer_card.body.addWidget(self.printer_combo)
        test_print = QPushButton(
            qta.icon("fa5s.print", color=NEUTRAL["600"]), strings.SETTINGS_PRINTER_TEST
        )
        test_print.clicked.connect(self._test_print)
        printer_card.body.addWidget(test_print, alignment=Qt.AlignmentFlag.AlignLeft)
        left.addWidget(printer_card)

        # ------------------------------------------------------ accent
        accent_card = SectionCard(strings.SETTINGS_ACCENT_SECTION, "fa5s.palette")
        swatch_row = QHBoxLayout()
        swatch_row.setSpacing(SPACING["sm"])
        self._swatch_group = QButtonGroup(self)
        self._swatch_group.setExclusive(True)
        self._swatches: dict[str, QPushButton] = {}
        for color in ACCENT_PRESETS:
            swatch = QPushButton()
            swatch.setObjectName("Swatch")
            swatch.setCheckable(True)
            swatch.setStyleSheet(f"#Swatch {{ background: {color}; }}")
            swatch.setToolTip(color)
            swatch.clicked.connect(partial(self._pick_accent, color))
            self._swatch_group.addButton(swatch)
            swatch_row.addWidget(swatch)
            self._swatches[color] = swatch
        custom = QPushButton(strings.SETTINGS_ACCENT_CUSTOM)
        custom.clicked.connect(self._pick_custom_accent)
        swatch_row.addWidget(custom)
        swatch_row.addStretch(1)
        accent_card.body.addLayout(swatch_row)
        left.addWidget(accent_card)

        # -------------------------------------------------- danger zone
        danger_card = SectionCard(
            strings.SETTINGS_DANGER_SECTION, "fa5s.exclamation-triangle"
        )
        danger_card.setObjectName("DangerZone")
        danger_explain = QLabel(strings.SETTINGS_RESET_EXPLAIN)
        danger_explain.setObjectName("Muted")
        danger_explain.setWordWrap(True)
        danger_card.body.addWidget(danger_explain)
        reset_button = QPushButton(
            qta.icon("fa5s.trash", color=NEUTRAL["600"]), strings.SETTINGS_RESET_BUTTON
        )
        reset_button.setObjectName("Danger")
        reset_button.clicked.connect(self._factory_reset)
        danger_card.body.addWidget(reset_button, alignment=Qt.AlignmentFlag.AlignLeft)
        left.addWidget(danger_card)
        left.addStretch(1)

        body.addLayout(left, stretch=1)

        # ------------------------------------------------------ preview
        preview_column = QVBoxLayout()
        preview_title = QLabel(strings.SETTINGS_PREVIEW_TITLE)
        preview_title.setObjectName("SectionTitle")
        preview_column.addWidget(preview_title)
        self.preview = ReceiptPreview(store_name=self.store_name)
        preview_column.addWidget(self.preview)
        preview_column.addStretch(1)
        body.addLayout(preview_column)

        scroll.setWidget(content)
        outer.addWidget(scroll, stretch=1)

    # ------------------------------------------------------------- loading

    def refresh(self) -> None:
        run_api(
            lambda: self.api.get_settings(self.store_id),
            self._on_settings,
            lambda err: show_error(self, err.message),
        )

    def _on_settings(self, settings: object) -> None:
        self.settings = dict(settings)
        self.shop_name_input.setText(settings.get("shop_name") or "")
        self.phone_input.setText(settings.get("phone") or "")
        self.address_input.setText(settings.get("address") or "")
        self.footer_input.setText(settings.get("footer_message") or "")
        self.credit_check.setChecked(bool(settings.get("show_credit_details", True)))
        index = self.language_combo.findData(settings.get("ui_language", "fr"))
        self.language_combo.setCurrentIndex(max(index, 0))
        self._accent = settings.get("theme_accent")
        swatch = self._swatches.get(self._accent or "")
        if swatch is not None:
            swatch.setChecked(True)
        self._update_preview()

    # ------------------------------------------------------------- preview

    def _update_preview(self) -> None:
        self.preview.render_preview(
            shop_name=self.shop_name_input.text().strip(),
            phone=self.phone_input.text().strip(),
            address=self.address_input.text().strip(),
            footer=self.footer_input.text().strip(),
            show_credit=self.credit_check.isChecked(),
        )

    # -------------------------------------------------------------- accent

    def _pick_accent(self, color: str) -> None:
        self._accent = color

    def _pick_custom_accent(self) -> None:
        initial = QColor(self._accent) if self._accent else QColor("#2563EB")
        color = QColorDialog.getColor(initial, self, strings.SETTINGS_ACCENT_SECTION)
        if color.isValid():
            self._accent = color.name().upper()
            checked = self._swatch_group.checkedButton()
            if checked is not None:
                self._swatch_group.setExclusive(False)
                checked.setChecked(False)
                self._swatch_group.setExclusive(True)

    # ------------------------------------------------------------- printer

    def _on_printer_changed(self) -> None:
        """Persist the printer choice machine-locally (not to the backend)."""
        printing.set_selected_printer(self.printer_combo.currentData())

    def _test_print(self) -> None:
        import tempfile
        from pathlib import Path

        printer = self.printer_combo.currentData()
        path = Path(tempfile.gettempdir()) / "test_impression.pdf"
        try:
            printing.write_test_pdf(path, printer)
            printing.print_pdf(path, printer)
            show_toast(self, strings.SETTINGS_PRINTER_TEST_SENT)
        except OSError as exc:
            show_error(self, strings.RECEIPT_PRINT_FAILED.format(path=exc))

    # ---------------------------------------------------------------- save

    def _save(self) -> None:
        payload = {
            "shop_name": self.shop_name_input.text().strip() or None,
            "phone": self.phone_input.text().strip() or None,
            "address": self.address_input.text().strip() or None,
            "footer_message": self.footer_input.text().strip() or None,
            "show_credit_details": self.credit_check.isChecked(),
            "ui_language": self.language_combo.currentData() or "fr",
        }
        if self._accent:
            payload["theme_accent"] = self._accent
        self.save_button.setEnabled(False)
        run_api(
            lambda: self.api.update_settings(self.store_id, payload),
            self._on_saved,
            self._on_save_error,
        )

    def _on_saved(self, settings: object) -> None:
        self.save_button.setEnabled(True)
        self.settings = dict(settings)
        # Re-theme live from the saved accent — no restart needed.
        accent = settings.get("theme_accent")
        app = QApplication.instance()
        if app is not None and accent:
            app.setStyleSheet(render_qss(accent))
        show_toast(self, strings.SETTINGS_SAVED_TOAST)

    def _on_save_error(self, err) -> None:
        self.save_button.setEnabled(True)
        if err.code in ("invalid_pin", "pin_not_configured"):
            show_error(self, strings.PIN_REQUIRED_ACTION)
        else:
            show_error(self, err.message)

    # --------------------------------------------------------- danger zone

    def _factory_reset(self) -> None:
        dialog = FactoryResetDialog(self.api, parent=self)
        if dialog.exec() and dialog.reset_done:
            show_info(self, strings.RESET_DONE)
            app = QApplication.instance()
            if app is not None:
                app.quit()
