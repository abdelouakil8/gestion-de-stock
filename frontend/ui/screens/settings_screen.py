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
from ui.styles import tokens
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


class BackupRestoreDialog(ModalDialog):
    """PIN confirmation to restore a backup — destructive, needs typed PIN."""

    def __init__(self, api, zip_path: str, parent=None) -> None:
        super().__init__(strings.BACKUP_RESTORE_TITLE, parent)
        self.api = api
        self.zip_path = zip_path
        self.restore_done = False

        warning = QLabel(strings.BACKUP_RESTORE_CONFIRM)
        warning.setObjectName("FieldError")
        warning.setWordWrap(True)
        self.content.addWidget(warning)

        self.pin_input = QLineEdit()
        self.pin_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pin_input.setPlaceholderText(strings.LOGIN_PLACEHOLDER)
        self.pin_input.textChanged.connect(
            lambda text: self.ok_button.setEnabled(bool(text.strip()))
        )
        self.content.addWidget(self.pin_input)

        self.ok_button.setText(strings.BACKUP_RESTORE)
        self.ok_button.setObjectName("Danger")
        self.ok_button.setEnabled(False)
        self.pin_input.setFocus()

    def accept(self) -> None:
        pin = self.pin_input.text().strip()
        if not pin:
            return
        self.ok_button.setEnabled(False)
        from pathlib import Path

        zip_data = Path(self.zip_path).read_bytes()
        run_api(
            lambda: self.api.restore_backup(zip_data, pin),
            self._on_done,
            self._on_error,
        )

    def _on_done(self, _result: object) -> None:
        self.restore_done = True
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
        from ui.i18n import current_language

        def fit(text: str) -> str:
            return text if len(text) <= width else text[: width - 1] + "…"

        def center(text: str) -> str:
            return fit(text).center(width).rstrip()

        def row(left: str, right: str) -> str:
            space = width - len(right)
            if current_language == "ar":
                # In Arabic, the visual left is the logical right.
                return fit(right).ljust(len(right) + 1) + fit(left).rjust(width - len(right) - 1)
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
        
        self.escpos_check = QCheckBox(strings.SETTINGS_PRINTER_ESCPOS)
        self.escpos_check.toggled.connect(self._on_escpos_toggled)
        printer_card.body.addWidget(self.escpos_check)

        btn_row = QHBoxLayout()
        test_print = QPushButton(
            qta.icon("fa5s.print", color=NEUTRAL["600"]), strings.SETTINGS_PRINTER_TEST
        )
        test_print.clicked.connect(self._test_print)
        btn_row.addWidget(test_print)

        self.drawer_btn = QPushButton(
            qta.icon("fa5s.box-open", color=NEUTRAL["600"]), strings.SETTINGS_PRINTER_DRAWER
        )
        self.drawer_btn.clicked.connect(self._kick_drawer)
        btn_row.addWidget(self.drawer_btn)
        btn_row.addStretch(1)
        printer_card.body.addLayout(btn_row)
        left.addWidget(printer_card)

        self._refresh_printer_ui()

        # ------------------------------------------------------ backup
        backup_card = SectionCard(strings.BACKUP_SECTION, "fa5s.database")
        backup_hint = QLabel(strings.BACKUP_HINT)
        backup_hint.setObjectName("FieldHint")
        backup_hint.setWordWrap(True)
        backup_card.body.addWidget(backup_hint)
        backup_row = QHBoxLayout()
        self.backup_create_btn = QPushButton(
            qta.icon("fa5s.download", color=NEUTRAL["600"]), strings.BACKUP_CREATE
        )
        self.backup_create_btn.clicked.connect(self._create_backup)
        backup_row.addWidget(self.backup_create_btn)
        self.backup_restore_btn = QPushButton(
            qta.icon("fa5s.upload", color=NEUTRAL["600"]), strings.BACKUP_RESTORE
        )
        self.backup_restore_btn.clicked.connect(self._restore_backup)
        backup_row.addWidget(self.backup_restore_btn)
        backup_row.addStretch(1)
        backup_card.body.addLayout(backup_row)
        left.addWidget(backup_card)
        
        # ------------------------------------------------------ tour
        tour_card = SectionCard(strings.FEATURE_TOUR_TITLE, "fa5s.info-circle")
        tour_hint = QLabel("Redécouvrez les fonctionnalités principales de l'application.")
        tour_hint.setObjectName("FieldHint")
        tour_card.body.addWidget(tour_hint)
        tour_btn = QPushButton(qta.icon("fa5s.play", color=NEUTRAL["600"]), "Démarrer la visite")
        tour_btn.clicked.connect(self._start_tour)
        tour_card.body.addWidget(tour_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        left.addWidget(tour_card)

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

    # ---------------------------------------------------------- actions
    
    def _start_tour(self) -> None:
        from ui.screens.feature_tour import FeatureTour

        window = self.window()
        if not hasattr(window, "_nav_buttons"):
            return  # not hosted in the main window (defensive)
        # Keep a reference on the window so the modeless tour isn't GC'd.
        window._feature_tour = FeatureTour(window)
        window._feature_tour.start()

    # ------------------------------------------------------------- printer

    def _on_printer_changed(self) -> None:
        name = self.printer_combo.currentData()
        printing.set_selected_printer(name)
        self._refresh_printer_ui()

    def _refresh_printer_ui(self) -> None:
        name = self.printer_combo.currentData()
        from services import escpos_printer
        if name:
            self.escpos_check.setEnabled(True)
            self.escpos_check.blockSignals(True)
            self.escpos_check.setChecked(escpos_printer.is_escpos_enabled(name))
            self.escpos_check.blockSignals(False)
            self.drawer_btn.setEnabled(self.escpos_check.isChecked())
        else:
            self.escpos_check.setEnabled(False)
            self.escpos_check.setChecked(False)
            self.drawer_btn.setEnabled(False)

    def _on_escpos_toggled(self, checked: bool) -> None:
        name = self.printer_combo.currentData()
        if name:
            from services import escpos_printer
            escpos_printer.set_escpos_enabled(name, checked)
            self.drawer_btn.setEnabled(checked)

    def _kick_drawer(self) -> None:
        name = self.printer_combo.currentData()
        if name:
            from services import escpos_printer
            escpos_printer.kick_drawer(name)

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
        old_lang = self.settings.get("ui_language", "fr")
        self.settings = dict(settings)
        new_lang = self.settings.get("ui_language", "fr")
        
        # Re-theme live from the saved accent — no restart needed.
        accent = self.settings.get("theme_accent")
        app = QApplication.instance()
        if app is not None and accent:
            tokens.CURRENT_ACCENT = accent
            app.setStyleSheet(render_qss())
            
        if old_lang != new_lang:
            from ui.i18n import apply_language
            apply_language(new_lang)
            
            main_win = self.window()
            if main_win:
                from ui.screens.main_window import MainWindow
                new_window = MainWindow(self.api, main_win.store)
                new_window.navigate(new_window.settings_screen)
                
                app._main_window = new_window  # Keep reference to prevent GC
                new_window.show()
                main_win.close()
                main_win.deleteLater()
        else:
            show_toast(self, strings.SETTINGS_SAVED_TOAST)

    def _on_save_error(self, err) -> None:
        self.save_button.setEnabled(True)
        if err.code in ("invalid_pin", "pin_not_configured"):
            show_error(self, strings.PIN_REQUIRED_ACTION)
        else:
            show_error(self, err.message)

    # ------------------------------------------------------------- backup

    def _create_backup(self) -> None:
        self.backup_create_btn.setEnabled(False)
        self.backup_create_btn.setText(strings.BACKUP_CREATING)
        run_api(
            lambda: self.api.create_backup(),
            self._on_backup_created,
            self._on_backup_error,
        )

    def _on_backup_created(self, data: bytes) -> None:
        from PySide6.QtWidgets import QFileDialog

        self.backup_create_btn.setEnabled(True)
        self.backup_create_btn.setText(strings.BACKUP_CREATE)
        path, _ = QFileDialog.getSaveFileName(
            self, strings.BACKUP_CREATE, "backup.zip", strings.BACKUP_FILE_FILTER
        )
        if path:
            from pathlib import Path

            Path(path).write_bytes(data)
            show_toast(self, strings.BACKUP_CREATED)

    def _on_backup_error(self, err) -> None:
        self.backup_create_btn.setEnabled(True)
        self.backup_create_btn.setText(strings.BACKUP_CREATE)
        show_error(self, err.message)

    def _restore_backup(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getOpenFileName(
            self, strings.BACKUP_RESTORE, "", strings.BACKUP_FILE_FILTER
        )
        if not path:
            return
        dialog = BackupRestoreDialog(self.api, path, parent=self)
        if dialog.exec() and dialog.restore_done:
            show_info(self, strings.BACKUP_RESTORE_SUCCESS)
            app = QApplication.instance()
            if app is not None:
                app.quit()

    # --------------------------------------------------------- danger zone

    def _factory_reset(self) -> None:
        dialog = FactoryResetDialog(self.api, parent=self)
        if dialog.exec() and dialog.reset_done:
            show_info(self, strings.RESET_DONE)
            app = QApplication.instance()
            if app is not None:
                app.quit()
