"""Receipt printing — per-machine printer selection.

The printer is a property of the physical till, not of the store data (each
machine can have its own), so the chosen printer is stored MACHINE-LOCAL via
QSettings (Windows registry), never synced through the backend.

- available_printers() / default_printer(): enumerate installed printers.
- get/set_selected_printer(): the operator's choice (None = system default).
- print_pdf(): send a PDF to the chosen printer (or the default) silently.
- write_test_pdf(): a self-contained one-page test page (no backend needed).
"""

import os
import subprocess
from pathlib import Path

from loguru import logger
from PySide6.QtCore import QSettings
from PySide6.QtGui import QPageSize, QPainter, QPdfWriter
from PySide6.QtPrintSupport import QPrinterInfo

_ORG = "GestionStockPOS"
_APP = "GestionStockPOS"
_KEY = "receipt_printer"


def available_printers() -> list[str]:
    return list(QPrinterInfo.availablePrinterNames())


def default_printer() -> str:
    info = QPrinterInfo.defaultPrinter()
    return "" if info.isNull() else info.printerName()


def get_selected_printer() -> str | None:
    """The saved printer name, or None to mean 'system default'."""
    value = QSettings(_ORG, _APP).value(_KEY, "")
    return str(value) if value else None


def set_selected_printer(name: str | None) -> None:
    settings = QSettings(_ORG, _APP)
    if name:
        settings.setValue(_KEY, name)
    else:
        settings.remove(_KEY)


def print_pdf(path: Path, printer: str | None = None) -> None:
    """Send a PDF to the chosen printer, or the system default when None."""
    if os.name != "nt":  # dev fallback on non-Windows
        subprocess.Popen(["xdg-open", str(path)])
        return
    import ctypes

    if printer:
        ctypes.windll.shell32.ShellExecuteW(
            None, "printto", str(path), f'"{printer}"', None, 0
        )
    else:
        ctypes.windll.shell32.ShellExecuteW(
            None, "print", str(path), None, None, 0
        )
    logger.info("Receipt sent to printer | printer={}", printer or "(default)")


def open_file(path: Path) -> None:
    """Open a file in the OS default application (viewer), not the printer.

    Used to *show* a generated PDF (clôture report, rapport journalier) rather
    than send it straight to the printer."""
    if os.name == "nt":
        os.startfile(str(path))  # noqa: S606 (Windows default handler)
    else:
        subprocess.Popen(["xdg-open", str(path)])


def write_test_pdf(path: Path, printer: str | None) -> None:
    """A minimal, self-contained test page (does not touch the backend)."""
    writer = QPdfWriter(str(path))
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A6))
    painter = QPainter(writer)
    font = painter.font()
    font.setPointSize(16)
    painter.setFont(font)
    painter.drawText(300, 500, "Test d'impression")
    font.setPointSize(11)
    painter.setFont(font)
    painter.drawText(300, 800, printer or "Imprimante par défaut du système")
    painter.drawText(300, 1000, "Gestion de Stock & Point de Vente")
    painter.end()
