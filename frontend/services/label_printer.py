"""Barcode label generation and printing (60x40mm)."""

import tempfile
import uuid
from pathlib import Path

from loguru import logger
from PySide6.QtCore import QSizeF, Qt
from PySide6.QtGui import QImage, QPainter, QPdfWriter

from services import printing

try:
    import barcode
    from barcode.writer import ImageWriter
except ImportError:
    barcode = None


def generate_barcode_value() -> str:
    """Returns a short 12-char hex string to use as a barcode if none exists."""
    return uuid.uuid4().hex[:12].upper()


def _render_barcode_image(value: str) -> QImage | None:
    if not barcode:
        logger.warning("python-barcode not installed, skipping barcode image generation.")
        return None
    try:
        Code128 = barcode.get_barcode_class('code128')
        writer = ImageWriter()
        writer.set_options({
            'module_width': 0.2,
            'module_height': 5.0,
            'font_size': 10,
            'text_distance': 4.0,
            'quiet_zone': 2.0,
        })
        code = Code128(value, writer=writer)
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
            code.write(f)
            temp_path = f.name
        img = QImage(temp_path)
        Path(temp_path).unlink(missing_ok=True)
        return img
    except Exception as e:
        logger.error(f"Failed to generate barcode image: {e}")
        return None


def print_barcode_label(product: dict, printer: str | None, copies: int = 1) -> Path | None:
    path = Path(tempfile.gettempdir()) / f"label_{product['id']}.pdf"
    
    writer = QPdfWriter(str(path))
    writer.setPageSize(QSizeF(60, 40))  # 60mm x 40mm
    writer.setResolution(300)
    
    painter = QPainter(writer)
    w = writer.width()
    h = writer.height()
    
    # 1. Product Name
    painter.drawText(0, 40, w, 100, Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.TextWordWrap, product.get("name", "")[:40])
    
    # 2. Price
    price = product.get("price_detail", 0)
    painter.drawText(0, 140, w, 60, Qt.AlignmentFlag.AlignCenter, f"{float(price):.2f} DZD")
    
    # 3. Barcode Image
    bc_value = product.get("barcode")
    if not bc_value:
        # Don't persist, just print a dummy one for now if missing
        bc_value = product["id"].split('-')[0].upper()
        
    img = _render_barcode_image(bc_value)
    if img:
        img = img.scaled(w - 100, int(h / 2), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        x_offset = (w - img.width()) // 2
        painter.drawImage(x_offset, 220, img)
    else:
        painter.drawText(0, 220, w, 100, Qt.AlignmentFlag.AlignCenter, bc_value)
        
    painter.end()
    
    # Send to printer
    for _ in range(copies):
        printing.print_pdf(path, printer)
        
    return path
