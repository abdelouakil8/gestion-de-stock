"""Barcode label sheet generation (reportlab + python-barcode).

Renders a chosen set of products as labels tiled on A4 pages: each label can
show the store name, product name, a price (at a chosen level), and an EAN-13 /
Code128 barcode. Sizes match common label rolls (58×30, 58×40, 40×25 mm) and
`copies` repeats each product. Returns PDF bytes (bytes in → bytes out).
"""

from decimal import Decimal
from io import BytesIO
from uuid import UUID

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Product, Store, StoreSettings

# Label physical sizes (width, height) in millimetres.
_SIZES = {
    "58x30": (58, 30),
    "58x40": (58, 40),
    "40x25": (40, 25),
}
_MARGIN = 8 * mm
_GAP = 3 * mm

_PRICE_FIELDS = {
    "detail": "price_detail",
    "gros": "price_gros",
    "super_gros": "price_super_gros",
}


def _fmt_money(value: Decimal) -> str:
    amount = Decimal(str(value)).quantize(Decimal("0.01"))
    text = f"{amount:,.2f}".replace(",", " ").replace(".", ",")
    return f"{text} DA"


def _barcode_png(code: str, symbology: str) -> BytesIO | None:
    """A barcode image for `code`, or None when it cannot be encoded.

    EAN-13 is used only for a 12/13-digit numeric code; everything else (and
    any EAN failure) falls back to Code128, which encodes arbitrary strings."""
    code = (code or "").strip()
    if not code:
        return None
    try:
        import barcode
        from barcode.writer import ImageWriter

        writer_options = {
            "write_text": True,
            "module_height": 8.0,
            "font_size": 6,
            "text_distance": 2.0,
            "quiet_zone": 1.5,
        }
        if symbology == "ean13" and code.isdigit() and len(code) in (12, 13):
            cls = barcode.get_barcode_class("ean13")
            payload = code[:12]  # the 13th digit is a checksum EAN13 recomputes
        else:
            cls = barcode.get_barcode_class("code128")
            payload = code
        buffer = BytesIO()
        cls(payload, writer=ImageWriter()).write(buffer, options=writer_options)
        buffer.seek(0)
        return buffer
    except Exception:
        # Retry once as Code128 before giving up (bad EAN payload, etc.).
        if symbology != "code128":
            return _barcode_png(code, "code128")
        return None


def build_labels_pdf(
    db: Session, store_id: UUID, product_ids: list[UUID], config: dict
) -> bytes:
    """Render the selected products as an A4 sheet of barcode labels."""
    products = list(
        db.scalars(
            select(Product).where(
                Product.id.in_(product_ids),
                Product.store_id == store_id,
                Product.deleted_at.is_(None),
            )
        )
    )
    # Preserve the caller's product order (and any duplicates were deduped by
    # the IN filter; copies handle repetition instead).
    by_id = {p.id: p for p in products}
    ordered = [by_id[pid] for pid in product_ids if pid in by_id]

    store = db.scalar(select(Store).where(Store.id == store_id))
    settings = db.scalar(
        select(StoreSettings).where(StoreSettings.store_id == store_id)
    )
    store_name = (settings.shop_name if settings else None) or (
        store.name if store else ""
    )

    size = _SIZES.get(config.get("size"), _SIZES["58x30"])
    label_w, label_h = size[0] * mm, size[1] * mm
    show_name = config.get("show_name", True)
    show_price = config.get("show_price", True)
    show_barcode = config.get("show_barcode", True)
    show_store = config.get("show_store", False)
    price_field = _PRICE_FIELDS.get(config.get("price_level", "detail"), "price_detail")
    barcode_type = config.get("barcode_type", "code128")
    copies = max(1, min(999, int(config.get("copies", 1))))

    page_w, page_h = A4
    usable_w = page_w - 2 * _MARGIN
    usable_h = page_h - 2 * _MARGIN
    cols = max(1, int((usable_w + _GAP) // (label_w + _GAP)))
    rows = max(1, int((usable_h + _GAP) // (label_h + _GAP)))
    per_page = cols * rows

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)

    # Flatten (product × copies) into a single stream of labels.
    stream = [product for product in ordered for _ in range(copies)]
    if not stream:
        pdf.showPage()
        pdf.save()
        return buffer.getvalue()

    def _safe(text: str) -> str:
        return str(text).encode("latin-1", "replace").decode("latin-1")

    for index, product in enumerate(stream):
        slot = index % per_page
        if slot == 0 and index > 0:
            pdf.showPage()
        col = slot % cols
        row = slot // cols
        x = _MARGIN + col * (label_w + _GAP)
        # Top-down placement.
        y_top = page_h - _MARGIN - row * (label_h + _GAP)
        _draw_label(
            pdf,
            x,
            y_top,
            label_w,
            label_h,
            product,
            store_name,
            show_store=show_store,
            show_name=show_name,
            show_price=show_price,
            show_barcode=show_barcode,
            price_field=price_field,
            barcode_type=barcode_type,
            safe=_safe,
        )

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def _draw_label(
    pdf,
    x,
    y_top,
    w,
    h,
    product,
    store_name,
    *,
    show_store,
    show_name,
    show_price,
    show_barcode,
    price_field,
    barcode_type,
    safe,
) -> None:
    pad = 2 * mm
    pdf.setLineWidth(0.4)
    pdf.rect(x, y_top - h, w, h, stroke=1, fill=0)
    cursor = y_top - pad - 3 * mm

    if show_store and store_name:
        pdf.setFont("Helvetica", 6)
        pdf.drawCentredString(x + w / 2, cursor, safe(store_name)[:40])
        cursor -= 3.2 * mm

    if show_name:
        pdf.setFont("Helvetica-Bold", 8)
        name = safe(product.name)
        if len(name) > 30:
            name = name[:29] + "…"
        pdf.drawCentredString(x + w / 2, cursor, name)
        cursor -= 4 * mm

    if show_price:
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawCentredString(
            x + w / 2, cursor, _fmt_money(getattr(product, price_field))
        )
        cursor -= 4.5 * mm

    if show_barcode:
        image = _barcode_png(product.barcode, barcode_type)
        if image is not None:
            bc_h = min(11 * mm, cursor - (y_top - h) - pad)
            bc_w = w - 2 * pad
            if bc_h > 3 * mm and bc_w > 0:
                pdf.drawImage(
                    ImageReader(image),
                    x + pad,
                    y_top - h + pad,
                    width=bc_w,
                    height=bc_h,
                    preserveAspectRatio=True,
                    anchor="s",
                    mask="auto",
                )
        elif product.barcode:
            pdf.setFont("Helvetica", 7)
            pdf.drawCentredString(
                x + w / 2, y_top - h + pad + 2 * mm, safe(product.barcode)
            )
