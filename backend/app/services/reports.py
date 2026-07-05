"""PDF and XLSX generation for store reports.

Reuses the same Money/Decimal discipline and existing statistics queries.
"""

from datetime import datetime
from decimal import Decimal
from io import BytesIO
from uuid import UUID

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from openpyxl import Workbook
from openpyxl.styles import Font, numbers

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Store
from app.services import alerts, customers, statistics


_A4_WIDTH, _A4_HEIGHT = A4
_MARGIN = 20 * mm
_LINE = 6 * mm

# Mapping for payment methods (mirrored from strings.py)
PAYMENT_LABELS = {
    "cash": "Espèces",
    "card": "Carte",
    "mobile": "Mobile",
    "other": "Autre",
}


def _safe(text: str) -> str:
    """Degrade text to what the built-in Type1 font can render."""
    return text.encode("latin-1", "replace").decode("latin-1")


def build_summary_report_pdf(
    db: Session, store_id: UUID, date_from: datetime, date_to: datetime
) -> bytes:
    """A4 PDF report spanning sales, products, customers, stock, and credits."""
    store = db.scalar(select(Store).where(Store.id == store_id))
    store_name = store.name if store else "Ma Boutique"

    # Fetch data
    summary = statistics.sales_summary(db, store_id, date_from, date_to)
    top_prods = statistics.top_products(db, store_id, date_from, date_to, limit=10)
    top_custs = customers.top_customers(db, store_id, date_from, date_to, limit=10)
    payments = statistics.payment_method_breakdown(db, store_id, date_from, date_to)
    low_stock = alerts.low_stock_products(db, store_id)
    credits = alerts.outstanding_credits(db, store_id)

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    y = _A4_HEIGHT - _MARGIN
    page_num = 1

    def new_page_if_needed(needed: float):
        nonlocal y, page_num
        if y - needed < _MARGIN:
            _draw_footer()
            pdf.showPage()
            y = _A4_HEIGHT - _MARGIN
            page_num += 1
            _draw_header()

    def _draw_header():
        nonlocal y
        pdf.setFont("Helvetica-Bold", 18)
        pdf.drawCentredString(_A4_WIDTH / 2, y, _safe("RAPPORT DE SYNTHÈSE"))
        y -= _LINE * 1.5
        pdf.setFont("Helvetica", 10)
        dr = f"Du {date_from.strftime('%d/%m/%Y')} au {date_to.strftime('%d/%m/%Y')}"
        pdf.drawCentredString(_A4_WIDTH / 2, y, _safe(f"{store_name} | {dr}"))
        y -= _LINE * 2

    def _draw_footer():
        pdf.setFont("Helvetica", 8)
        now_str = datetime.now().strftime("%d/%m/%Y à %H:%M")
        pdf.drawString(_MARGIN, 10 * mm, _safe(f"Généré le {now_str}"))
        pdf.drawRightString(_A4_WIDTH - _MARGIN, 10 * mm, f"Page {page_num}")

    def section_header(title: str):
        nonlocal y
        new_page_if_needed(3 * _LINE)
        y -= _LINE
        pdf.setFont("Helvetica-Bold", 14)
        pdf.drawString(_MARGIN, y, _safe(title))
        y -= _LINE * 0.5
        pdf.line(_MARGIN, y, _A4_WIDTH - _MARGIN, y)
        y -= _LINE

    def table_row(cols: list[tuple[str, float]], bold=False):
        nonlocal y
        new_page_if_needed(_LINE)
        pdf.setFont("Helvetica-Bold" if bold else "Helvetica", 10)
        for text, x in cols:
            pdf.drawString(x, y, _safe(str(text)))
        y -= _LINE

    # Initialize first page
    _draw_header()

    # 1. Résumé financier
    section_header("Résumé financier")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(_MARGIN, y, "Chiffre d'affaires :")
    pdf.drawRightString(_MARGIN + 60*mm, y, str(summary.revenue))
    y -= _LINE
    pdf.drawString(_MARGIN, y, "Marge brute :")
    pdf.drawRightString(_MARGIN + 60*mm, y, str(summary.gross_profit))
    y -= _LINE
    pdf.drawString(_MARGIN, y, "Nombre de ventes :")
    pdf.drawRightString(_MARGIN + 60*mm, y, str(summary.sales_count))
    y -= _LINE
    pdf.drawString(_MARGIN, y, "Total remises :")
    pdf.drawRightString(_MARGIN + 60*mm, y, str(summary.total_discounts))
    y -= _LINE

    # 2. Meilleures ventes
    if top_prods:
        section_header("Meilleures ventes")
        col_x = [(_MARGIN, "Produit"), (_MARGIN + 80*mm, "Quantité"), (_MARGIN + 120*mm, "CA")]
        table_row([(c[1], c[0]) for c in col_x], bold=True)
        for p in top_prods:
            name = p.name[:35] + "…" if len(p.name) > 35 else p.name
            table_row([(name, col_x[0][0]), (p.quantity_sold, col_x[1][0]), (p.revenue, col_x[2][0])])

    # 3. Meilleurs clients
    if top_custs:
        section_header("Meilleurs clients")
        col_x = [(_MARGIN, "Client"), (_MARGIN + 60*mm, "Téléphone"), (_MARGIN + 100*mm, "CA"), (_MARGIN + 140*mm, "Ventes")]
        table_row([(c[1], c[0]) for c in col_x], bold=True)
        for c in top_custs:
            name = c.name[:25] + "…" if len(c.name) > 25 else c.name
            table_row([(name, col_x[0][0]), (c.phone, col_x[1][0]), (c.revenue, col_x[2][0]), (c.sales_count, col_x[3][0])])

    # 4. Répartition par mode de paiement
    if payments:
        section_header("Répartition par mode de paiement")
        col_x = [(_MARGIN, "Mode"), (_MARGIN + 60*mm, "Montant"), (_MARGIN + 120*mm, "Transactions")]
        table_row([(c[1], c[0]) for c in col_x], bold=True)
        for p in payments:
            table_row([(PAYMENT_LABELS.get(p.payment_method, p.payment_method), col_x[0][0]), (p.total, col_x[1][0]), (p.count, col_x[2][0])])

    # 5. Stock faible
    if low_stock:
        section_header("Stock faible")
        col_x = [(_MARGIN, "Produit"), (_MARGIN + 80*mm, "Stock"), (_MARGIN + 120*mm, "Seuil")]
        table_row([(c[1], c[0]) for c in col_x], bold=True)
        for p in low_stock:
            name = p.name[:35] + "…" if len(p.name) > 35 else p.name
            table_row([(name, col_x[0][0]), (p.stock_quantity, col_x[1][0]), (p.low_stock_threshold, col_x[2][0])])

    # 6. Crédits en attente
    if credits:
        section_header("Crédits en attente")
        col_x = [(_MARGIN, "Client"), (_MARGIN + 50*mm, "Total"), (_MARGIN + 80*mm, "Payé"), (_MARGIN + 110*mm, "Reste"), (_MARGIN + 140*mm, "Ancienneté")]
        table_row([(c[1], c[0]) for c in col_x], bold=True)
        for c in credits:
            name = (c.customer_name or "Inconnu")[:20] + "…" if len((c.customer_name or "")) > 20 else (c.customer_name or "Inconnu")
            table_row([(name, col_x[0][0]), (c.total_amount, col_x[1][0]), (c.paid_amount, col_x[2][0]), (c.balance, col_x[3][0]), (f"{c.age_days} j", col_x[4][0])])

    _draw_footer()
    pdf.save()
    return buffer.getvalue()


def build_summary_report_xlsx(
    db: Session, store_id: UUID, date_from: datetime, date_to: datetime
) -> bytes:
    """Multi-sheet Excel export of the same data as the PDF."""
    summary = statistics.sales_summary(db, store_id, date_from, date_to)
    top_prods = statistics.top_products(db, store_id, date_from, date_to, limit=10)
    top_custs = customers.top_customers(db, store_id, date_from, date_to, limit=10)
    payments = statistics.payment_method_breakdown(db, store_id, date_from, date_to)
    low_stock = alerts.low_stock_products(db, store_id)
    credits = alerts.outstanding_credits(db, store_id)

    wb = Workbook()
    
    def format_headers(ws, headers):
        ws.append(headers)
        for cell in ws[1]:
            cell.font = Font(bold=True)
    
    def write_decimal(ws, row):
        # Convert Decimals to float and apply formatting
        new_row = []
        for val in row:
            if isinstance(val, Decimal):
                new_row.append(float(val))
            else:
                new_row.append(val)
        ws.append(new_row)
        # Apply format to just written row
        for cell in ws[ws.max_row]:
            if isinstance(cell.value, float):
                cell.number_format = numbers.FORMAT_NUMBER_COMMA_SEPARATED1

    # 1. Synthèse
    ws_syn = wb.active
    ws_syn.title = "Synthèse"
    format_headers(ws_syn, ["Métrique", "Valeur"])
    write_decimal(ws_syn, ["Chiffre d'affaires", summary.revenue])
    write_decimal(ws_syn, ["Marge brute", summary.gross_profit])
    write_decimal(ws_syn, ["Nombre de ventes", summary.sales_count])
    write_decimal(ws_syn, ["Total remises", summary.total_discounts])
    ws_syn.column_dimensions['A'].width = 25
    ws_syn.column_dimensions['B'].width = 15

    # 2. Meilleures ventes
    ws_prod = wb.create_sheet("Meilleures ventes")
    format_headers(ws_prod, ["Produit", "Quantité vendue", "Chiffre d'affaires"])
    for p in top_prods:
        write_decimal(ws_prod, [p.name, p.quantity_sold, p.revenue])
    ws_prod.column_dimensions['A'].width = 30
    ws_prod.column_dimensions['B'].width = 20
    ws_prod.column_dimensions['C'].width = 20

    # 3. Meilleurs clients
    ws_cust = wb.create_sheet("Meilleurs clients")
    format_headers(ws_cust, ["Client", "Téléphone", "CA", "Nombre de ventes"])
    for c in top_custs:
        write_decimal(ws_cust, [c.name, c.phone, c.revenue, c.sales_count])
    ws_cust.column_dimensions['A'].width = 30
    ws_cust.column_dimensions['B'].width = 15
    ws_cust.column_dimensions['C'].width = 15
    ws_cust.column_dimensions['D'].width = 20

    # 4. Modes de paiement
    ws_pay = wb.create_sheet("Modes de paiement")
    format_headers(ws_pay, ["Mode", "Montant", "Transactions"])
    for p in payments:
        write_decimal(ws_pay, [PAYMENT_LABELS.get(p.payment_method, p.payment_method), p.total, p.count])
    ws_pay.column_dimensions['A'].width = 20
    ws_pay.column_dimensions['B'].width = 15
    ws_pay.column_dimensions['C'].width = 15

    # 5. Stock faible
    ws_stock = wb.create_sheet("Stock faible")
    format_headers(ws_stock, ["Produit", "Stock actuel", "Seuil d'alerte"])
    for p in low_stock:
        write_decimal(ws_stock, [p.name, p.stock_quantity, p.low_stock_threshold])
    ws_stock.column_dimensions['A'].width = 30
    ws_stock.column_dimensions['B'].width = 15
    ws_stock.column_dimensions['C'].width = 15

    # 6. Crédits en attente
    ws_cred = wb.create_sheet("Crédits en attente")
    format_headers(ws_cred, ["Client", "Total", "Payé", "Reste", "Ancienneté (jours)"])
    for c in credits:
        write_decimal(ws_cred, [c.customer_name, c.total_amount, c.paid_amount, c.balance, c.age_days])
    ws_cred.column_dimensions['A'].width = 30
    ws_cred.column_dimensions['B'].width = 15
    ws_cred.column_dimensions['C'].width = 15
    ws_cred.column_dimensions['D'].width = 15
    ws_cred.column_dimensions['E'].width = 20

    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
