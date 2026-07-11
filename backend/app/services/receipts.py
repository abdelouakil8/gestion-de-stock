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
from pathlib import Path

from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from app.models import Customer, Sale, Store, StoreSettings
from app.models.refund import Refund

_WIDTH = 80 * mm
_MARGIN = 5 * mm
_LINE = 5 * mm

_DEFAULT_FOOTER = "Merci de votre visite !"

# Register Arabic font
FONT_DIR = Path(__file__).resolve().parents[1] / "assets" / "fonts"
pdfmetrics.registerFont(TTFont("Amiri", str(FONT_DIR / "Amiri-Regular.ttf")))

_RECEIPT_I18N: dict[str, dict[str, str]] = {
    "fr": {
        "tel": "Tél :",
        "date_line": "Le {date}",
        "ticket_n": "Ticket N°",
        "total": "TOTAL",
        "paid": "Payé",
        "balance": "Reste à payer",
        "client": "Client :",
        "reason": "Motif :",
        "avoir": "AVOIR",
        "vente_n": "Vente N°",
        "avoir_n": "Avoir N°",
        "total_avoir": "TOTAL AVOIR",
    },
    "ar": {
        "tel": "هاتف:",
        "date_line": "{date}",
        "ticket_n": "تذكرة رقم",
        "total": "المجموع",
        "paid": "المدفوع",
        "balance": "المتبقي",
        "client": "العميل:",
        "reason": "السبب:",
        "avoir": "إشعار دائن",
        "vente_n": "بيع رقم",
        "avoir_n": "إشعار رقم",
        "total_avoir": "مجموع الإشعار",
    },
}


def _shape_arabic(text: str) -> str:
    """Shape and reorder Arabic text for ReportLab rendering."""
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display

        # Configure reshaper to handle ligatures correctly
        configuration = {
            "delete_harakat": False,
            "shift_harakat_position": False,
            "use_unshaped_instead_of_isolated": False,
        }
        reshaper = arabic_reshaper.ArabicReshaper(configuration=configuration)
        reshaped = reshaper.reshape(text)
        return get_display(reshaped)
    except ImportError:
        # Fallback if libraries are missing in environment
        return text.encode("latin-1", "replace").decode("latin-1")


def _safe(text: str, is_arabic: bool = False) -> str:
    """Degrade text or shape it based on language.

    French (Latin-1) passes through untouched; characters outside Latin-1
    (e.g. Arabic, pending the RTL font update) become '?' instead of
    crashing PDF generation mid-checkout, UNLESS is_arabic is True.
    """
    if is_arabic:
        return _shape_arabic(text)
    return text.encode("latin-1", "replace").decode("latin-1")


def _fmt_money(amount: Decimal, is_arabic: bool = False) -> str:
    """French-style monetary format: comma decimal, NBSP thousands, DA/دج suffix."""
    value = Decimal(str(amount)).quantize(Decimal("0.01"))
    text = f"{value:,.2f}"
    formatted = text.replace(",", " ").replace(".", ",")
    symbol = "دج" if is_arabic else "DA"
    return f"{formatted} {symbol}"


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
    # Packaging lines get a 3rd row (the base-unit breakdown).
    packaging_extra = sum(
        1
        for item in items
        if getattr(item, "packaging_label", None)
        and (getattr(item, "unit_count", 1) or 1) > 1
    )
    # 10 fixed header/footer lines + optional header/credit lines
    # + up to 2 lines per item (+1 for each packaged item).
    height = (
        10 + header_extra + credit_extra + packaging_extra + 2 * len(items)
    ) * _LINE + 2 * _MARGIN

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(_WIDTH, height))
    y = height - _MARGIN

    is_arabic = bool(settings and settings.ui_language == "ar")
    lang = (settings.ui_language if settings else None) or "fr"
    i18n = _RECEIPT_I18N.get(lang, _RECEIPT_I18N["fr"])
    default_font = "Amiri" if is_arabic else "Helvetica"
    bold_font = "Amiri" if is_arabic else "Helvetica-Bold"

    def line(text: str, font: str = default_font, size: int = 9, center: bool = False):
        nonlocal y
        if font == "Helvetica" and is_arabic:
            font = default_font
        if font == "Helvetica-Bold" and is_arabic:
            font = bold_font

        pdf.setFont(font, size)
        safe_txt = _safe(text, is_arabic)
        if center:
            pdf.drawCentredString(_WIDTH / 2, y, safe_txt)
        else:
            if is_arabic:
                pdf.drawRightString(_WIDTH - _MARGIN, y, safe_txt)
            else:
                pdf.drawString(_MARGIN, y, safe_txt)
        y -= _LINE

    def line_right(left: str, right: str, font: str = default_font, size: int = 9):
        nonlocal y
        if font == "Helvetica" and is_arabic:
            font = default_font
        if font == "Helvetica-Bold" and is_arabic:
            font = bold_font

        pdf.setFont(font, size)
        safe_left = _safe(left, is_arabic)
        safe_right = _safe(right, is_arabic)
        if is_arabic:
            # Flip positions: the left string goes to the right margin and
            # the right string goes to the left margin.
            pdf.drawString(_MARGIN, y, safe_right)
            pdf.drawRightString(_WIDTH - _MARGIN, y, safe_left)
        else:
            pdf.drawString(_MARGIN, y, safe_left)
            pdf.drawRightString(_WIDTH - _MARGIN, y, safe_right)
        y -= _LINE

    line(shop_name, font="Helvetica-Bold", size=12, center=True)
    if settings and settings.phone:
        line(f"{i18n['tel']} {settings.phone}", size=8, center=True)
    if settings and settings.address:
        line(settings.address, size=8, center=True)
    created = sale.created_at.strftime("%d/%m/%Y %H:%M") if sale.created_at else ""
    line(i18n["date_line"].format(date=created), size=8, center=True)
    ticket_num = (
        f"{sale.invoice_number:06d}"
        if sale.invoice_number
        else str(sale.id)[:8].upper()
    )
    line(f"{i18n['ticket_n']} {ticket_num}", size=8, center=True)
    line("-" * 42)

    total_check = Decimal("0.00")
    for item in items:
        name = item.product.name if item.product else "Produit"
        # A priced packaging (carton) sold on this line: annotate the product
        # name with the snapshotted packaging label so the receipt survives
        # later packaging edits/deletes.
        label = getattr(item, "packaging_label", None)
        if label:
            name = f"{name} ({label})"
        if len(name) > 38:
            name = name[:37] + "…"
        line(name, font="Helvetica-Bold")
        line_right(
            f"  {item.quantity} x {_fmt_money(item.unit_price_applied, is_arabic)}",
            _fmt_money(item.line_total, is_arabic),
        )
        discount = getattr(item, "discount_amount", None) or Decimal("0")
        if discount > 0:
            line(f"  Remise : -{_fmt_money(discount, is_arabic)}", size=8)
        # Show the base-unit breakdown for packagings (e.g. "2 x 24 = 48 u.")
        # so the merchant sees how many base units left the shelf.
        unit_count = getattr(item, "unit_count", 1) or 1
        if label and unit_count > 1:
            line(
                f"  soit {item.quantity} x {unit_count} = "
                f"{item.quantity * unit_count} u.",
                size=8,
            )
        total_check += item.line_total

    line("-" * 42)
    line_right(
        i18n["total"],
        _fmt_money(sale.total_amount, is_arabic),
        font="Helvetica-Bold",
        size=12,
    )

    if show_credit:
        if customer is not None:
            line(f"{i18n['client']} {customer.name}")
        line_right(i18n["paid"], _fmt_money(sale.paid_amount, is_arabic))
        line_right(
            i18n["balance"],
            _fmt_money(sale.total_amount - sale.paid_amount, is_arabic),
            font="Helvetica-Bold",
        )

    y -= _LINE
    line(footer, size=9, center=True)

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def build_refund_receipt_pdf(
    refund: Refund,
    sale: Sale,
    store: Store,
    settings: StoreSettings | None = None,
) -> bytes:
    """Render an avoir (refund) document — 80mm thermal style."""
    items = refund.items
    sale_items_map = {si.id: si for si in sale.items}

    shop_name = (settings.shop_name if settings else None) or store.name
    header_extra = int(bool(settings and settings.phone)) + int(
        bool(settings and settings.address)
    )
    height = (12 + header_extra + 2 * len(items)) * _LINE + 2 * _MARGIN

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(_WIDTH, height))
    y = height - _MARGIN

    is_arabic = bool(settings and settings.ui_language == "ar")
    lang = (settings.ui_language if settings else None) or "fr"
    i18n = _RECEIPT_I18N.get(lang, _RECEIPT_I18N["fr"])
    default_font = "Amiri" if is_arabic else "Helvetica"
    bold_font = "Amiri" if is_arabic else "Helvetica-Bold"

    def line(text: str, font: str = default_font, size: int = 9, center: bool = False):
        nonlocal y
        if font == "Helvetica" and is_arabic:
            font = default_font
        if font == "Helvetica-Bold" and is_arabic:
            font = bold_font

        pdf.setFont(font, size)
        safe_txt = _safe(text, is_arabic)
        if center:
            pdf.drawCentredString(_WIDTH / 2, y, safe_txt)
        else:
            if is_arabic:
                pdf.drawRightString(_WIDTH - _MARGIN, y, safe_txt)
            else:
                pdf.drawString(_MARGIN, y, safe_txt)
        y -= _LINE

    def line_right(left: str, right: str, font: str = default_font, size: int = 9):
        nonlocal y
        if font == "Helvetica" and is_arabic:
            font = default_font
        if font == "Helvetica-Bold" and is_arabic:
            font = bold_font

        pdf.setFont(font, size)
        safe_left = _safe(left, is_arabic)
        safe_right = _safe(right, is_arabic)
        if is_arabic:
            pdf.drawString(_MARGIN, y, safe_right)
            pdf.drawRightString(_WIDTH - _MARGIN, y, safe_left)
        else:
            pdf.drawString(_MARGIN, y, safe_left)
            pdf.drawRightString(_WIDTH - _MARGIN, y, safe_right)
        y -= _LINE

    line(i18n["avoir"], font="Helvetica-Bold", size=14, center=True)
    line(shop_name, font="Helvetica-Bold", size=10, center=True)
    if settings and settings.phone:
        line(f"{i18n['tel']} {settings.phone}", size=8, center=True)
    if settings and settings.address:
        line(settings.address, size=8, center=True)
    created = refund.created_at.strftime("%d/%m/%Y %H:%M") if refund.created_at else ""
    line(i18n["date_line"].format(date=created), size=8, center=True)
    line(f"{i18n['avoir_n']} {str(refund.id)[:8].upper()}", size=8, center=True)
    sale_num = (
        f"{sale.invoice_number:06d}"
        if sale.invoice_number
        else str(sale.id)[:8].upper()
    )
    line(f"{i18n['vente_n']} {sale_num}", size=8, center=True)
    line("-" * 42)

    for ri in items:
        si = sale_items_map.get(ri.sale_item_id)
        name = si.product.name if si and si.product else "Produit"
        if ri.unit_count > 1 and si and si.packaging_label:
            name = f"{name} ({si.packaging_label})"
        if len(name) > 38:
            name = name[:37] + "…"
        line(name, font="Helvetica-Bold")
        line_right(
            f"  {ri.quantity} x {_fmt_money(ri.unit_price_refunded, is_arabic)}",
            f"-{_fmt_money(ri.line_total, is_arabic)}",
        )

    line("-" * 42)
    line_right(
        i18n["total_avoir"],
        f"-{_fmt_money(refund.total_amount, is_arabic)}",
        font="Helvetica-Bold",
        size=12,
    )

    if refund.reason:
        y -= _LINE / 2
        line(f"{i18n['reason']} {refund.reason}", size=8)

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()
