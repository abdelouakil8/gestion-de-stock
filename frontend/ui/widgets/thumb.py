"""Product thumbnail / avatar — image when available, letter fallback else.

Images come through services.image_cache (async, shared); the fallback is
a colored square with the product's initial, so lists stay lively even
before any image is uploaded. Low-spec friendly: one rounded pixmap is
rendered per widget, no effects.
"""

import shiboken6
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QLabel

from services import image_cache
from ui.styles import tokens

# Theme-aware fallback palette — derived from ACCENT_PRESETS so the 8
# thumb colors stay distinguishable and adapt to light/dark mode. In light
# mode the backgrounds are soft pastels; in dark mode they're muted tints
# that read on a dark surface without glaring.
_ACCENT_CYCLE = [
    "#2563EB",
    "#16A34A",
    "#D97706",
    "#7C3AED",
    "#0D9488",
    "#DB2777",
    "#DC2626",
    "#0F172A",
]


def _thumb_bg(index: int) -> str:
    """Theme-aware background tint for the letter fallback."""
    accent = _ACCENT_CYCLE[index % len(_ACCENT_CYCLE)]
    if tokens.CURRENT_MODE == "dark":
        return tokens.mix(accent, tokens.CURRENT_SURFACE, 0.72)
    return tokens.lighten(accent, 0.88)


def _thumb_fg(index: int) -> str:
    """Theme-aware text color for the letter fallback."""
    accent = _ACCENT_CYCLE[index % len(_ACCENT_CYCLE)]
    if tokens.CURRENT_MODE == "dark":
        return tokens.lighten(accent, 0.30)
    return tokens.darken(accent, 0.30)


def _rounded(pixmap: QPixmap, size: int, radius: int) -> QPixmap:
    scaled = pixmap.scaled(
        size,
        size,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    target = QPixmap(size, size)
    target.fill(Qt.GlobalColor.transparent)
    painter = QPainter(target)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(0, 0, size, size, radius, radius)
    painter.setClipPath(path)
    x = (size - scaled.width()) // 2
    y = (size - scaled.height()) // 2
    painter.drawPixmap(x, y, scaled)
    painter.end()
    return target


class Thumb(QLabel):
    """Square thumbnail with rounded corners and a letter fallback."""

    def __init__(self, size: int, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Thumb")
        self._size = size
        self._generation = 0
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def set_letter(self, name: str) -> None:
        """Letter placeholder colored from the name (no image case)."""
        index = sum(name.encode("utf-8", "ignore")) % len(_ACCENT_CYCLE)
        letter = (name.strip()[:1] or "•").upper()
        self.setPixmap(QPixmap())  # clear any previous image
        self.setText(letter)
        self.setStyleSheet(
            f"background: {_thumb_bg(index)}; color: {_thumb_fg(index)};"
            f" border-radius: {tokens.RADIUS['md']}px;"
            f" font-size: {max(11, self._size // 2 - 2)}px; font-weight: 700;"
        )

    def set_product(self, product: dict) -> None:
        """Show the product image (async) or its letter fallback."""
        self._generation += 1
        generation = self._generation
        self.set_letter(product.get("name", ""))
        if not product.get("image_path"):
            return

        def deliver(pixmap) -> None:
            # The widget may have been destroyed (dialog closed, table
            # rebuilt) or re-targeted while the fetch was in flight.
            if not shiboken6.isValid(self):
                return
            if generation != self._generation or pixmap is None:
                return
            self.setText("")
            self.setStyleSheet("")
            self.setPixmap(_rounded(pixmap, self._size, tokens.RADIUS["md"]))

        image_cache.get(product, deliver)

    def set_pixmap_direct(self, pixmap: QPixmap | None, name: str = "") -> None:
        """Local preview (file picker) without going through the cache."""
        self._generation += 1
        if pixmap is None or pixmap.isNull():
            self.set_letter(name)
            return
        self.setText("")
        self.setStyleSheet("")
        self.setPixmap(_rounded(pixmap, self._size, tokens.RADIUS["md"]))
