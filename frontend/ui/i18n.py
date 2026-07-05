"""Internationalization (i18n) manager.

Dynamically loads the active language strings module based on StoreSettings.
Provides the current_strings object which ui/strings.py proxies via __getattr__.
"""

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from ui import strings_fr

# Default to French
current_strings: Any = strings_fr
current_language: str = "fr"


def apply_language(language_code: str) -> None:
    """Sets the active language and applies RTL layout if needed."""
    global current_strings, current_language

    current_language = language_code

    if language_code == "ar":
        from ui import strings_ar

        current_strings = strings_ar
        app = QApplication.instance()
        if app:
            app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    else:
        current_strings = strings_fr
        app = QApplication.instance()
        if app:
            app.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
