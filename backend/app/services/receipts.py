"""Receipt PDF generation (ReportLab) — 80mm thermal-roll format.

Reads StoreSettings when provided: header (shop name override, phone,
address), footer message, and — for credit sales when show_credit_details
is on — the paid/remaining lines and the customer name.

Layout is deliberately simple and font-safe (Helvetica). When Arabic RTL
product names arrive, this module gains a registered TTF font + text
shaping; the API surface (bytes in → bytes out) will not change.
"""

from decimal import Decimal
from io import BytesIO

from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from app.models import Customer, Sale, Store, StoreSettings

_WIDTH = 80 * mm
_MARGIN = 5 * mm
_LINE = 5 * mm

_DEFAULT_FOOTER = "Merci de votre visite !"


def _safe(text: str) -> str:
    """Degrade text to what the built-in Type1 font can render.

    French (Latin-1) passes through untouched; characters outside Latin-1
    (e.g. Arabic, pending the RTL font update) become '?' instead of
    crashing PDF generation mid-checkout.
    """
    return text.encode("latin-1", "replace").decode("latin-1")


def build_receipt_pdf(
    sale: Sale,
    store: Store,
    settings: StoreSettings | None = None,
    customer: Customer | None = None,
) -> bytes:
    """Render one finalized sale as a printable receipt PDF."""
    items = [item for item in sale.items if item.deleted_at is None]

    shop_name = (settings.shop_name if settings else None) or store.name
    footer = (settings.footer_message if settings else None) or _DEFAULT_FOOTER
    show_credit = (
        settings is not None
        and settings.show_credit_details
        and sale.paid_amount < sale.total_amount
    )

    header_extra = int(bool(settings and settings.phone)) + int(
        bool(settings and settings.address)
    )
    credit_extra = (3 + int(customer is not None)) if show_credit else 0
    # 10 fixed header/footer lines + optional header/credit lines
    # + up to 2 lines per item.
    height = (10 + header_extra + credit_extra + 2 * len(items)) * _LINE + 2 * _MARGIN

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(_WIDTH, height))
    y = height - _MARGIN

    def line(text: str, font: str = "Helvetica", size: int = 9, center: bool = False):
        nonlocal y
        pdf.setFont(font, size)
        if center:
            pdf.drawCentredString(_WIDTH / 2, y, _safe(text))
        else:
            pdf.drawString(_MARGIN, y, _safe(text))
        y -= _LINE

    def line_right(left: str, right: str, font: str = "Helvetica", size: int = 9):
        nonlocal y
        pdf.setFont(font, size)
        pdf.drawString(_MARGIN, y, _safe(left))
        pdf.drawRightString(_WIDTH - _MARGIN, y, _safe(right))
        y -= _LINE

    line(shop_name, font="Helvetica-Bold", size=12, center=True)
    if settings and settings.phone:
        line(f"Tél : {settings.phone}", size=8, center=True)
    if settings and settings.address:
        line(settings.address, size=8, center=True)
    created = sale.created_at.strftime("%d/%m/%Y %H:%M") if sale.created_at else ""
    line(f"Le {created}", size=8, center=True)
    line(f"Ticket N° {str(sale.id)[:8].upper()}", size=8, center=True)
    line("-" * 42)

    total_check = Decimal("0.00")
    for item in items:
        name = item.product.name if item.product else "Produit"
        if len(name) > 38:
            name = name[:37] + "…"
        line(name, font="Helvetica-Bold")
        line_right(
            f"  {item.quantity} x {item.unit_price_applied}",
            f"{item.line_total}",
        )
        total_check += item.line_total

    line("-" * 42)
    line_right("TOTAL", f"{sale.total_amount}", font="Helvetica-Bold", size=12)

    if show_credit:
        if customer is not None:
            line(f"Client : {customer.name}")
        line_right("Payé", f"{sale.paid_amount}")
        line_right(
            "Reste à payer",
            f"{sale.total_amount - sale.paid_amount}",
            font="Helvetica-Bold",
        )

    y -= _LINE
    line(footer, size=9, center=True)

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()
