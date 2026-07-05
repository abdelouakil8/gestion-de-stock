"""Centralized user-facing strings — dynamic proxy.

This module proxies all attribute lookups to the currently active language
module (e.g. strings_fr or strings_ar) via the i18n manager.

This ensures zero call-site changes across the application while supporting
live language switching (with an app restart).
"""

from typing import Any

from ui import i18n


def __getattr__(name: str) -> Any:
    return getattr(i18n.current_strings, name)
