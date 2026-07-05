"""Direct ESC/POS thermal printing.

Gracefully falls back to the PDF route if win32print is missing or errors out.
"""

from datetime import datetime
from decimal import Decimal

from loguru import logger
from PySide6.QtCore import QSettings

try:
    import win32print
except ImportError:
    win32print = None


_ORG = "GestionStockPOS"
_APP = "GestionStockPOS"
_KEY_PREFIX = "escpos_enabled_"

# ESC/POS Commands
_INIT = b'\x1B\x40'
_ALIGN_LEFT = b'\x1B\x61\x00'
_ALIGN_CENTER = b'\x1B\x61\x01'
_BOLD_ON = b'\x1B\x45\x01'
_BOLD_OFF = b'\x1B\x45\x00'
_DOUBLE_HEIGHT_ON = b'\x1B\x21\x10'
_DOUBLE_HEIGHT_OFF = b'\x1B\x21\x00'
_CUT = b'\x1D\x56\x41\x00'
_DRAWER_KICK = b'\x1B\x70\x00\x19\xFA'

_COLS = 32


def is_escpos_enabled(printer_name: str) -> bool:
    if not printer_name:
        return False
    # Use a sanitized key since printer names can have spaces
    key = f"{_KEY_PREFIX}{printer_name.replace(' ', '_')}"
    return QSettings(_ORG, _APP).value(key, False, type=bool)


def set_escpos_enabled(printer_name: str, enabled: bool) -> None:
    if printer_name:
        key = f"{_KEY_PREFIX}{printer_name.replace(' ', '_')}"
        QSettings(_ORG, _APP).setValue(key, enabled)


def _safe_cp437(text: str) -> bytes:
    return str(text).encode('cp437', errors='replace')


def build_escpos_receipt(sale: dict, settings: dict | None, store_name: str, customer_name: str | None) -> bytes:
    settings = settings or {}
    width = _COLS

    def fit(text: str) -> bytes:
        if len(text) > width:
            text = text[: width - 1] + "…"
        return _safe_cp437(text) + b'\n'

    def center(text: str) -> bytes:
        if len(text) > width:
            text = text[: width - 1] + "…"
        text = text.center(width).rstrip()
        return _safe_cp437(text) + b'\n'

    def row(left: str, right: str) -> bytes:
        space = width - len(right)
        left = left if len(left) <= space else left[:space - 1] + "…"
        text = left.ljust(space) + right
        return _safe_cp437(text) + b'\n'

    buffer = bytearray()
    buffer.extend(_INIT)
    buffer.extend(_ALIGN_CENTER)

    shop_name = settings.get("receipt_shop_name") or store_name
    buffer.extend(_DOUBLE_HEIGHT_ON)
    buffer.extend(center(shop_name))
    buffer.extend(_DOUBLE_HEIGHT_OFF)

    phone = settings.get("receipt_phone")
    if phone:
        buffer.extend(center(f"Tél : {phone}"))
    address = settings.get("receipt_address")
    if address:
        buffer.extend(center(address))

    created_at = sale.get("created_at")
    if created_at:
        try:
            dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            buffer.extend(center(dt.strftime("Le %d/%m/%Y %H:%M")))
        except ValueError:
            pass

    buffer.extend(center(f"Ticket #{sale['id'].split('-')[0].upper()}"))
    buffer.extend(_ALIGN_LEFT)
    buffer.extend(b'-' * width + b'\n')

    for item in sale.get("items", []):
        name = item.get("product_name", "Produit")
        qty = item.get("quantity", 1)
        price = Decimal(str(item.get("unit_price_override", 0)))
        total = Decimal(str(item.get("total_price", 0)))
        buffer.extend(fit(name))
        buffer.extend(row(f"  {qty} x {price:.2f}", f"{total:.2f}"))

    buffer.extend(b'-' * width + b'\n')
    
    total_amount = Decimal(str(sale.get("total_amount", 0)))
    buffer.extend(_BOLD_ON)
    buffer.extend(row("TOTAL", f"{total_amount:.2f}"))
    buffer.extend(_BOLD_OFF)

    if settings.get("receipt_show_credit", True) and sale.get("status") == "credit":
        if customer_name:
            buffer.extend(fit(customer_name))
        paid = Decimal(str(sale.get("paid_amount", 0)))
        balance = total_amount - paid
        buffer.extend(row("Payé", f"{paid:.2f}"))
        buffer.extend(row("Reste", f"{balance:.2f}"))

    buffer.extend(b'\n')
    buffer.extend(_ALIGN_CENTER)
    footer = settings.get("receipt_footer") or "Merci de votre visite !"
    buffer.extend(center(footer))
    buffer.extend(b'\n\n\n\n')
    buffer.extend(_CUT)

    return bytes(buffer)


def send_raw_to_printer(printer_name: str, data: bytes) -> None:
    if not win32print:
        raise OSError("win32print non disponible.")
    
    try:
        hprinter = win32print.OpenPrinter(printer_name)
        try:
            win32print.StartDocPrinter(hprinter, 1, ("Ticket", None, "RAW"))
            win32print.StartPagePrinter(hprinter)
            win32print.WritePrinter(hprinter, data)
            win32print.EndPagePrinter(hprinter)
            win32print.EndDocPrinter(hprinter)
        finally:
            win32print.ClosePrinter(hprinter)
    except Exception as e:
        logger.error(f"Erreur impression ESC/POS: {e}")
        raise OSError(f"Erreur d'impression : {e}")


def kick_drawer(printer_name: str) -> None:
    """Sends just the kick command (drawer only)."""
    try:
        send_raw_to_printer(printer_name, _INIT + _DRAWER_KICK)
        logger.info(f"Tiroir caisse ouvert sur {printer_name}")
    except OSError as e:
        logger.warning(f"Impossible d'ouvrir le tiroir : {e}")


def print_receipt_escpos(
    sale_data: dict,
    printer_name: str,
    settings: dict | None,
    store_name: str,
    customer_name: str | None,
    payment_method: str = "cash",
) -> bool:
    """Main entrypoint for thermal printing. Returns True if successful."""
    if not win32print:
        logger.debug("win32print absent, fallback PDF")
        return False

    if not is_escpos_enabled(printer_name):
        logger.debug(f"ESC/POS désactivé pour {printer_name}, fallback PDF")
        return False

    try:
        receipt_bytes = build_escpos_receipt(sale_data, settings, store_name, customer_name)
        
        # If it's a cash sale, append the drawer kick to the same job
        if payment_method == "cash":
            receipt_bytes += _DRAWER_KICK
            
        send_raw_to_printer(printer_name, receipt_bytes)
        logger.info(f"Impression ESC/POS réussie sur {printer_name}")
        return True
    except OSError as e:
        logger.warning(f"Échec impression ESC/POS, fallback PDF: {e}")
        return False
