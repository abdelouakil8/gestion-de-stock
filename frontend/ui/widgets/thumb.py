"""Product thumbnail / avatar — image when available, letter fallback else.

Images come through services.image_cache (async, shared); the fallback is
a colored square with the product's initial, so lists stay lively even
before any image is uploaded. Low-spec friendly: one rounded pixmap is
rendered per widget, no effects.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QLabel

from services import image_cache
from ui.styles.tokens import RADIUS

# Pastel fallback palette (name-hashed) — friendly, readable dark text.
_FALLBACK_BG = [
    "#DBEAFE",
    "#DCFCE7",
    "#FEF3C7",
    "#FCE7F3",
    "#E0E7FF",
    "#CCFBF1",
    "#FEE2E2",
    "#EDE9FE",
]
_FALLBACK_FG = [
    "#1D4ED8",
    "#15803D",
    "#B45309",
    "#BE185D",
    "#4338CA",
    "#0F766E",
    "#B91C1C",
    "#6D28D9",
]


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
        index = sum(name.encode("utf-8", "ignore")) % len(_FALLBACK_BG)
        letter = (name.strip()[:1] or "•").upper()
        self.setPixmap(QPixmap())  # clear any previous image
        self.setText(letter)
        self.setStyleSheet(
            f"background: {_FALLBACK_BG[index]}; color: {_FALLBACK_FG[index]};"
            f" border-radius: {RADIUS['md']}px;"
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
            # A recycled widget may have been re-targeted meanwhile.
            if generation != self._generation or pixmap is None:
                return
            self.setText("")
            self.setStyleSheet("")
            self.setPixmap(_rounded(pixmap, self._size, RADIUS["md"]))

        image_cache.get(product, deliver)

    def set_pixmap_direct(self, pixmap: QPixmap | None, name: str = "") -> None:
        """Local preview (file picker) without going through the cache."""
        self._generation += 1
        if pixmap is None or pixmap.isNull():
            self.set_letter(name)
            return
        self.setText("")
        self.setStyleSheet("")
        self.setPixmap(_rounded(pixmap, self._size, RADIUS["md"]))
