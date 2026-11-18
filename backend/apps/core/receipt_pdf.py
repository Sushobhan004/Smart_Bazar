# -*- coding: utf-8 -*-
"""
Smart Bazaar â€” Production PDF Receipt & Invoice Generator with Shop Logo Watermark
Generates professional A4 tax invoices with full store, owner, cashier, customer, and itemized billing details.
"""

import io
import os
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, Image as RLImage
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors


class WatermarkNumberedCanvas(canvas.Canvas):
    """
    Two-pass canvas that renders a subtle, semi-transparent shop logo or brand emblem
    in the background of every page, along with official page numbering.
    """
    def __init__(self, *args, logo_path=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.logo_path = logo_path
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_watermark_and_footer(num_pages)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def draw_watermark_and_footer(self, total_pages):
        # 1. Background Watermark (Low Alpha so it does not obscure text)
        self.saveState()
        self.setFillAlpha(0.08)
        # Center of A4 page (595.27 x 841.89 points)
        cx, cy = 297.6, 420.9
        
        if self.logo_path and os.path.exists(self.logo_path):
            try:
                wm_size = 280
                self.drawImage(
                    self.logo_path,
                    cx - (wm_size / 2),
                    cy - (wm_size / 2),
                    width=wm_size,
                    height=wm_size,
                    mask='auto',
                    preserveAspectRatio=True
                )
            except Exception:
                self._draw_default_watermark(cx, cy)
        else:
            self._draw_default_watermark(cx, cy)
        self.restoreState()

        # 2. Page Number in Footer
        self.saveState()
        self.setFont('Helvetica', 8)
        self.setFillColor(colors.HexColor('#64748B'))
        page_str = f"Page {self._pageNumber} of {total_pages}"
        self.drawRightString(595.27 - 36, 24, page_str)
        self.drawString(36, 24, "Smart Bazaar Official Digital Tax Invoice â€¢ Powered by Google Gmail API")
        self.restoreState()

    def _draw_default_watermark(self, cx, cy):
        self.setFillColor(colors.HexColor('#0F5132'))
        self.setFont('Helvetica-Bold', 46)
        self.drawCentredString(cx, cy, "SMART BAZAAR")
        self.setFont('Helvetica-Bold', 18)
        self.drawCentredString(cx, cy - 35, "AUTHENTIC RECEIPT")


def generate_receipt_pdf(
    shop_name: str,
    shop_code: str,
    shop_owner_name: str,
    shop_address: str,
    shop_phone: str,
    cashier_name: str,
    cashier_id: str,
    customer_name: str,
    customer_phone: str,
    customer_code: str,
    customer_email: str,
    bill_number: str,
    items: list,
    subtotal: float,
    tax_amount: float,
    final_total: float,
    payment_method: str = "UPI / PhonePe",
    created_at_str: str = None,
    logo_path: str = None
) -> bytes:
    """
    Generates a complete, beautiful A4 tax invoice PDF with shop logo watermark.
    Returns raw PDF bytes.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=42
    )

    styles = getSampleStyleSheet()

    # Custom styles
    primary_color = colors.HexColor('#0F5132')
    text_dark = colors.HexColor('#0F172A')
    text_muted = colors.HexColor('#475569')

    style_title = ParagraphStyle(
        'DocTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=22,
        textColor=primary_color
    )
    style_subtitle = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=text_muted
    )
    style_h2 = ParagraphStyle(
        'DocH2',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=15,
        textColor=primary_color
    )
    style_label = ParagraphStyle(
        'DocLabel',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor('#334155')
    )
    style_val = ParagraphStyle(
        'DocVal',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=12,
        textColor=text_dark
    )
    style_cell = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=11,
        textColor=text_dark
    )
    style_cell_bold = ParagraphStyle(
        'TableCellBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=11,
        textColor=text_dark
    )

    story = []

    # 1. Top Header Banner Table (Logo + Store Name + Invoice Badge)
    header_content_left = [
        Paragraph(f"<b>{shop_name.upper()}</b>", style_title),
        Paragraph(f"Store ID: <b>{shop_code}</b> &bull; Phone: {shop_phone}", style_subtitle),
        Paragraph(f"Address: {shop_address}", style_subtitle),
        Paragraph(f"<b>Shop Owner:</b> <font color='#0F5132'><b>{shop_owner_name}</b></font>", style_label),
    ]

    header_badge = [
        Paragraph("<font color='#0F5132'><b>OFFICIAL TAX INVOICE</b></font>", style_h2),
        Paragraph(f"<b>Bill No:</b> {bill_number}", style_label),
        Paragraph(f"<b>Date:</b> {created_at_str or datetime.now().strftime('%d %b %Y, %I:%M %p')}", style_val),
        Paragraph(f"<b>Billed By (Cashier):</b> <font color='#166534'><b>{cashier_name}</b></font> ({cashier_id})", style_label),
    ]

    # If logo file exists on disk, embed it in the header
    logo_flowable = None
    if logo_path and os.path.exists(logo_path):
        try:
            logo_flowable = RLImage(logo_path, width=54, height=54)
        except Exception:
            logo_flowable = None

    if logo_flowable:
        header_table = Table(
            [[logo_flowable, header_content_left, header_badge]],
            colWidths=[65, 275, 183]
        )
    else:
        header_table = Table(
            [[header_content_left, header_badge]],
            colWidths=[330, 193]
        )

    header_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ('TOPPADDING', (0,0), (-1,-1), 0),
    ]))
    story.append(header_table)

    story.append(Spacer(1, 12))
    story.append(HRFlowable(width="100%", thickness=1.5, color=primary_color, spaceBefore=4, spaceAfter=10))

    # 2. Customer & Cashier Metadata Cards (Two-Column Table)
    cust_box = [
        Paragraph("<b>CUSTOMER DETAILS</b>", style_label),
        Paragraph(f"Name: <b>{customer_name or 'Walk-in Guest'}</b>", style_val),
        Paragraph(f"Phone: <b>{customer_phone or 'N/A'}</b>", style_val),
        Paragraph(f"Email: {customer_email or 'N/A'}", style_val),
        Paragraph(f"Customer Code: <font color='#0F5132'><b>{customer_code or 'WALK-IN'}</b></font>", style_val),
    ]

    trans_box = [
        Paragraph("<b>BILLING & TRANSACTION DETAILS</b>", style_label),
        Paragraph(f"Invoice Number: <b>INV-{bill_number}</b>", style_val),
        Paragraph(f"Payment Method: <b>{payment_method}</b>", style_val),
        Paragraph(f"Cashier Identity: <b>{cashier_name}</b> (ID: {cashier_id})", style_val),
        Paragraph("Payment Status: <font color='#15803D'><b>âœ“ PAID &amp; COMPLETED</b></font>", style_val),
    ]

    meta_table = Table(
        [[cust_box, trans_box]],
        colWidths=[260, 263]
    )
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#F8FAFC')),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#E2E8F0')),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E1')),
        ('TOPPADDING', (0,0), (-1,-1), 8),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
        ('RIGHTPADDING', (0,0), (-1,-1), 10),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ]))
    story.append(meta_table)

    story.append(Spacer(1, 14))

    # 3. Itemized Bill Table
    items_header = [
        Paragraph("<b>#</b>", ParagraphStyle('H0', parent=style_cell_bold, textColor=colors.white)),
        Paragraph("<b>ITEM DESCRIPTION</b>", ParagraphStyle('H1', parent=style_cell_bold, textColor=colors.white)),
        Paragraph("<b>BARCODE / SKU</b>", ParagraphStyle('H2', parent=style_cell_bold, textColor=colors.white)),
        Paragraph("<b>QTY</b>", ParagraphStyle('H3', parent=style_cell_bold, textColor=colors.white, alignment=1)),
        Paragraph("<b>RATE (â‚¹)</b>", ParagraphStyle('H4', parent=style_cell_bold, textColor=colors.white, alignment=2)),
        Paragraph("<b>AMOUNT (â‚¹)</b>", ParagraphStyle('H5', parent=style_cell_bold, textColor=colors.white, alignment=2)),
    ]

    table_data = [items_header]
    row_idx = 1
    for it in (items or []):
        name = it.get('name') or it.get('product_name') or 'Product'
        barcode = it.get('barcode') or it.get('sku') or '-'
        qty = it.get('quantity') or it.get('qty') or 1
        unit_price = float(it.get('unit_price') or it.get('price') or 0.0)
        tot = float(it.get('total_price') or (unit_price * float(qty)))

        table_data.append([
            Paragraph(str(row_idx), style_cell),
            Paragraph(f"<b>{name}</b>", style_cell),
            Paragraph(f"<font face='Courier'>{barcode}</font>", style_cell),
            Paragraph(str(qty), ParagraphStyle('C3', parent=style_cell, alignment=1)),
            Paragraph(f"â‚¹{unit_price:.2f}", ParagraphStyle('C4', parent=style_cell, alignment=2)),
            Paragraph(f"<b>â‚¹{tot:.2f}</b>", ParagraphStyle('C5', parent=style_cell_bold, alignment=2)),
        ])
        row_idx += 1

    items_table = Table(
        table_data,
        colWidths=[24, 215, 114, 40, 65, 65]
    )
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), primary_color),
        ('ALIGN', (0,0), (2,-1), 'LEFT'),
        ('ALIGN', (3,0), (3,-1), 'CENTER'),
        ('ALIGN', (4,0), (-1,-1), 'RIGHT'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#E2E8F0')),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#F8FAFC')]),
    ]))
    story.append(items_table)

    story.append(Spacer(1, 10))

    # 4. Financial Summary Block (Right-aligned table)
    summary_data = [
        [Paragraph("Subtotal:", style_label), Paragraph(f"â‚¹{subtotal:.2f}", ParagraphStyle('S1', parent=style_val, alignment=2))],
        [Paragraph("GST / Taxes:", style_label), Paragraph(f"â‚¹{tax_amount:.2f}", ParagraphStyle('S2', parent=style_val, alignment=2))],
        [
            Paragraph("<b>GRAND TOTAL:</b>", ParagraphStyle('S3', parent=style_label, fontSize=11, leading=13, textColor=primary_color)),
            Paragraph(f"<b>â‚¹{final_total:.2f}</b>", ParagraphStyle('S4', parent=style_title, fontSize=13, leading=15, alignment=2, textColor=primary_color))
        ],
    ]
    summary_table = Table(summary_data, colWidths=[120, 100])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0,2), (-1,2), colors.HexColor('#DCFCE7')),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#CBD5E1')),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#E2E8F0')),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('RIGHTPADDING', (0,0), (-1,-1), 8),
    ]))

    # Wrap summary in a container table pushed to the right
    container_table = Table(
        [[Paragraph(
            f"<b>Store Policy &amp; Warranty:</b><br/>"
            f"â€¢ Goods once sold can be returned within 7 days with this bill.<br/>"
            f"â€¢ Digital bill copy sent to customer's registered Gmail: <b>{customer_email or 'N/A'}</b>.<br/>"
            f"â€¢ Store managed by: <b>{shop_owner_name}</b> | Cashier: <b>{cashier_name}</b>.",
            style_subtitle
        ), summary_table]],
        colWidths=[303, 220]
    )
    container_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('TOPPADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
    ]))
    story.append(container_table)

    story.append(Spacer(1, 18))
    story.append(HRFlowable(width="100%", thickness=0.8, color=colors.HexColor('#CBD5E1'), spaceBefore=2, spaceAfter=8))

    # 5. Bottom Acknowledgement
    story.append(Paragraph(
        f"<font color='#0F5132'><b>Thank you for shopping at {shop_name}! Please visit again.</b></font>",
        ParagraphStyle('FooterNotice', parent=styles['Normal'], alignment=1, fontSize=9.5, leading=13)
    ))

    # Build PDF with custom WatermarkCanvas
    def canvasmaker(*args, **kwargs):
        return WatermarkNumberedCanvas(*args, logo_path=logo_path, **kwargs)

    doc.build(story, canvasmaker=canvasmaker)
    return buf.getvalue()
