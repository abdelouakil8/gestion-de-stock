"""Settings screen — receipt, language, appearance, printer, backup, danger."""

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
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from services import printing
from services.workers import run_api
from ui import strings
from ui.styles.tokens import (
    ACCENT_PRESETS,
    NEUTRAL,
    SPACING,
    build_palette,
    contrast_ratio,
    render_qss,
    semantic_defaults,
)
from ui.widgets.card import SectionCard
from ui.widgets.modal import show_error, show_info
from ui.widgets.promotions_management import PromotionsManagementTab
from ui.widgets.toast import show_toast
from ui.widgets.users_management import UsersManagementTab

from ._dialogs import BackupRestoreDialog, FactoryResetDialog, ReceiptPreview


class SettingsScreen(QWidget):
    def __init__(self, api, store: dict, parent=None) -> None:
        super().__init__(parent)
        self.api = api
        self.store_id = store["id"]
        self.store_name = store.get("name", "")
        self.settings: dict = {}
        self._accent = None
        self._mode = "light"
        self._language = "fr"
        self._overrides: dict[str, str | None] = {
            "background": None,
            "surface": None,
            "text": None,
            "border": None,
        }
        self._color_chips: dict[str, QPushButton] = {}
        self._color_hex: dict[str, QLabel] = {}
        self._mode_buttons: dict[str, QPushButton] = {}
        self._lang_buttons: dict[str, QPushButton] = {}

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
        language_card.body.addWidget(
            self._segmented(
                [
                    ("fr", strings.SETTINGS_LANGUAGE_FR),
                    ("ar", strings.SETTINGS_LANGUAGE_AR),
                ],
                self._lang_buttons,
                self._pick_language,
            )
        )
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
            qta.icon("fa5s.box-open", color=NEUTRAL["600"]),
            strings.SETTINGS_PRINTER_DRAWER,
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
        tour_hint = QLabel(
            "Redécouvrez les fonctionnalités principales de l'application."
        )
        tour_hint.setObjectName("FieldHint")
        tour_card.body.addWidget(tour_hint)
        tour_btn = QPushButton(
            qta.icon("fa5s.play", color=NEUTRAL["600"]), "Démarrer la visite"
        )
        tour_btn.clicked.connect(self._start_tour)
        tour_card.body.addWidget(tour_btn, alignment=Qt.AlignmentFlag.AlignLeading)
        left.addWidget(tour_card)

        # -------------------------------------------------- appearance
        appearance_card = SectionCard(
            strings.SETTINGS_APPEARANCE_SECTION, "fa5s.palette"
        )

        mode_row = QHBoxLayout()
        mode_label = QLabel(strings.SETTINGS_THEME_MODE)
        mode_label.setObjectName("Caption")
        mode_row.addWidget(mode_label)
        mode_row.addStretch(1)
        mode_row.addWidget(
            self._segmented(
                [
                    ("light", strings.SETTINGS_MODE_LIGHT),
                    ("dark", strings.SETTINGS_MODE_DARK),
                ],
                self._mode_buttons,
                self._pick_mode,
            )
        )
        appearance_card.body.addLayout(mode_row)

        accent_label = QLabel(strings.SETTINGS_ACCENT_LABEL)
        accent_label.setObjectName("Caption")
        appearance_card.body.addWidget(accent_label)
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
        appearance_card.body.addLayout(swatch_row)

        colors_divider = QFrame()
        colors_divider.setObjectName("HDivider")
        colors_divider.setFixedHeight(1)
        appearance_card.body.addWidget(colors_divider)

        custom_header = QHBoxLayout()
        custom_label = QLabel(strings.SETTINGS_CUSTOM_COLORS)
        custom_label.setObjectName("Caption")
        custom_header.addWidget(custom_label)
        custom_header.addStretch(1)
        reset_all = QPushButton(
            qta.icon("fa5s.undo", color=NEUTRAL["500"]),
            strings.SETTINGS_COLOR_RESET_ALL,
        )
        reset_all.setObjectName("Ghost")
        reset_all.clicked.connect(self._reset_all_colors)
        custom_header.addWidget(reset_all)
        appearance_card.body.addLayout(custom_header)

        for role, text, desc in (
            ("background", strings.SETTINGS_COLOR_BG, strings.SETTINGS_COLOR_BG_DESC),
            (
                "surface",
                strings.SETTINGS_COLOR_SURFACE,
                strings.SETTINGS_COLOR_SURFACE_DESC,
            ),
            ("text", strings.SETTINGS_COLOR_TEXT, strings.SETTINGS_COLOR_TEXT_DESC),
            (
                "border",
                strings.SETTINGS_COLOR_BORDER,
                strings.SETTINGS_COLOR_BORDER_DESC,
            ),
        ):
            appearance_card.body.addLayout(self._color_row(role, text, desc))

        self.contrast_warning = QLabel(strings.SETTINGS_CONTRAST_WARNING)
        self.contrast_warning.setObjectName("FieldError")
        self.contrast_warning.setWordWrap(True)
        self.contrast_warning.hide()
        appearance_card.body.addWidget(self.contrast_warning)

        custom_hint = QLabel(strings.SETTINGS_CUSTOM_HINT)
        custom_hint.setObjectName("FieldHint")
        custom_hint.setWordWrap(True)
        appearance_card.body.addWidget(custom_hint)
        left.addWidget(appearance_card)
        self._refresh_color_chips()

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
        danger_card.body.addWidget(reset_button, alignment=Qt.AlignmentFlag.AlignLeading)
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

        self.tabs = QTabWidget()
        self.tabs.addTab(scroll, strings.SETTINGS_TAB_GENERAL)
        self.users_tab = UsersManagementTab(self.api, self.store_id)
        self.tabs.addTab(self.users_tab, strings.SETTINGS_TAB_USERS)
        self.promotions_tab = PromotionsManagementTab(self.api, self.store_id)
        self.tabs.addTab(self.promotions_tab, strings.SETTINGS_TAB_PROMOTIONS)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        outer.addWidget(self.tabs, stretch=1)

    # ------------------------------------------------------------- loading

    def _on_tab_changed(self, index: int) -> None:
        widget = self.tabs.widget(index)
        self.save_button.setVisible(index == 0)
        if widget is self.users_tab:
            self.users_tab.refresh()
        elif hasattr(widget, "refresh") and index != 0:
            widget.refresh()

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
        self._language = settings.get("ui_language", "fr")
        lang_button = self._lang_buttons.get(self._language)
        if lang_button is not None:
            lang_button.setChecked(True)
        self._accent = settings.get("theme_accent")
        swatch = self._swatches.get(self._accent or "")
        if swatch is not None:
            swatch.setChecked(True)
        self._mode = settings.get("theme_mode", "light") or "light"
        mode_button = self._mode_buttons.get(self._mode)
        if mode_button is not None:
            mode_button.setChecked(True)
        self._overrides = {
            "background": settings.get("theme_bg"),
            "surface": settings.get("theme_surface"),
            "text": settings.get("theme_text"),
            "border": settings.get("theme_border"),
        }
        self._refresh_color_chips()
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

    # ---------------------------------------------------------- appearance

    def _segmented(self, items, registry, on_select) -> QWidget:
        """A small segmented control (iOS-style pill track, reuses the QSS)."""
        group = QWidget()
        group.setObjectName("SegmentGroup")
        group.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QHBoxLayout(group)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(3)
        button_group = QButtonGroup(group)
        button_group.setExclusive(True)
        for key, label in items:
            button = QPushButton(label)
            button.setObjectName("SegmentPill")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _=False, k=key: on_select(k))
            button_group.addButton(button)
            layout.addWidget(button)
            registry[key] = button
        return group

    def _color_row(self, role: str, label_text: str, desc_text: str):
        row = QHBoxLayout()
        row.setSpacing(SPACING["sm"])
        texts = QVBoxLayout()
        texts.setSpacing(0)
        label = QLabel(label_text)
        label.setObjectName("Secondary")
        texts.addWidget(label)
        desc = QLabel(desc_text)
        desc.setObjectName("Muted")
        texts.addWidget(desc)
        row.addLayout(texts)
        row.addStretch(1)
        hex_label = QLabel("")
        hex_label.setObjectName("Muted")
        self._color_hex[role] = hex_label
        row.addWidget(hex_label)
        chip = QPushButton()
        chip.setObjectName("Swatch")
        chip.setCursor(Qt.CursorShape.PointingHandCursor)
        chip.setToolTip(strings.SETTINGS_CUSTOM_COLORS)
        chip.clicked.connect(partial(self._pick_role_color, role))
        self._color_chips[role] = chip
        row.addWidget(chip)
        reset = QPushButton(qta.icon("fa5s.undo", color=NEUTRAL["500"]), "")
        reset.setObjectName("Ghost")
        reset.setToolTip(strings.SETTINGS_COLOR_RESET)
        reset.clicked.connect(partial(self._reset_role_color, role))
        row.addWidget(reset)
        return row

    def _pick_language(self, lang: str) -> None:
        self._language = lang

    def _pick_mode(self, mode: str) -> None:
        self._mode = mode
        self._refresh_color_chips()
        self._apply_live_theme()

    def _pick_accent(self, color: str) -> None:
        self._accent = color
        self._apply_live_theme()

    def _pick_custom_accent(self) -> None:
        initial = QColor(self._accent) if self._accent else QColor("#2563EB")
        color = QColorDialog.getColor(initial, self, strings.SETTINGS_ACCENT_LABEL)
        if color.isValid():
            self._accent = color.name().upper()
            checked = self._swatch_group.checkedButton()
            if checked is not None:
                self._swatch_group.setExclusive(False)
                checked.setChecked(False)
                self._swatch_group.setExclusive(True)
            self._apply_live_theme()

    def _pick_role_color(self, role: str) -> None:
        current = self._overrides.get(role) or semantic_defaults(self._mode)[role]
        color = QColorDialog.getColor(
            QColor(current), self, strings.SETTINGS_CUSTOM_COLORS
        )
        if color.isValid():
            self._overrides[role] = color.name().upper()
            self._refresh_color_chips()
            self._apply_live_theme()

    def _reset_role_color(self, role: str) -> None:
        self._overrides[role] = None
        self._refresh_color_chips()
        self._apply_live_theme()

    def _reset_all_colors(self) -> None:
        self._overrides = {role: None for role in self._overrides}
        self._refresh_color_chips()
        self._apply_live_theme()

    def _refresh_color_chips(self) -> None:
        defaults = semantic_defaults(self._mode)
        effective = {
            role: self._overrides.get(role) or defaults[role]
            for role in self._color_chips
        }
        for role, chip in self._color_chips.items():
            color = effective[role]
            chip.setStyleSheet(
                f"#Swatch {{ background: {color}; "
                f"border: 2px solid {defaults['border_strong']}; }}"
            )
            self._color_hex[role].setText(color.upper())
        readable = min(
            contrast_ratio(effective["text"], effective["background"]),
            contrast_ratio(effective["text"], effective["surface"]),
        )
        self.contrast_warning.setVisible(readable < 4.5)

    def _apply_live_theme(self) -> None:
        """Re-theme the whole app immediately (a live preview of the choices)."""
        app = QApplication.instance()
        if app is None:
            return
        overrides = {k: v for k, v in self._overrides.items() if v}
        app.setStyleSheet(render_qss(self._accent, self._mode, overrides))
        app.setPalette(build_palette())

    # ---------------------------------------------------------- actions

    def _start_tour(self) -> None:
        from ui.screens.feature_tour import FeatureTour

        window = self.window()
        if not hasattr(window, "_nav_by_key"):
            return
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
            "ui_language": self._language,
            "theme_mode": self._mode,
            "theme_bg": self._overrides.get("background"),
            "theme_surface": self._overrides.get("surface"),
            "theme_text": self._overrides.get("text"),
            "theme_border": self._overrides.get("border"),
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

        app = QApplication.instance()
        if app is not None:
            overrides = {
                "background": self.settings.get("theme_bg"),
                "surface": self.settings.get("theme_surface"),
                "text": self.settings.get("theme_text"),
                "border": self.settings.get("theme_border"),
            }
            app.setStyleSheet(
                render_qss(
                    self.settings.get("theme_accent"),
                    self.settings.get("theme_mode", "light"),
                    {k: v for k, v in overrides.items() if v},
                )
            )
            app.setPalette(build_palette())

        if old_lang != new_lang:
            from ui.i18n import apply_language

            apply_language(new_lang)

            main_win = self.window()
            if main_win:
                from ui.screens.main_window import MainWindow

                new_window = MainWindow(self.api, main_win.store)
                new_window.navigate(new_window.settings_screen)

                app._main_window = new_window
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
