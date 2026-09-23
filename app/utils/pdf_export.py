"""
PDF Report Generation using ReportLab.
"""
from io import BytesIO
from datetime import date
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT

# Brand Colors
NAVY = colors.HexColor("#12203D")
BRASS = colors.HexColor("#B98A2E")
LIGHT_BG = colors.HexColor("#EEF0F4")
SUCCESS = colors.HexColor("#3F7D58")
DANGER = colors.HexColor("#A94A34")
MUTED = colors.HexColor("#5B6273")
WHITE = colors.white


def _base_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("BrandTitle", fontName="Helvetica-Bold", fontSize=18, textColor=NAVY, spaceAfter=4))
    styles.add(ParagraphStyle("BrandSub", fontName="Helvetica", fontSize=10, textColor=MUTED, spaceAfter=12))
    styles.add(ParagraphStyle("SectionHeader", fontName="Helvetica-Bold", fontSize=12, textColor=NAVY, spaceBefore=12, spaceAfter=6))
    styles.add(ParagraphStyle("CellText", fontName="Helvetica", fontSize=8, textColor=colors.HexColor("#161B26")))
    styles.add(ParagraphStyle("CellBold", fontName="Helvetica-Bold", fontSize=8, textColor=NAVY))
    return styles


def _table_style(header_color=None):
    if header_color is None:
        header_color = NAVY
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), header_color),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT_BG]),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("ALIGN", (0, 1), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 1), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 5),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#DEE1E8")),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ])


def _header_section(story, styles, title, subtitle=""):
    story.append(Paragraph("AssetPulse — Smart Asset Management System", styles["BrandSub"]))
    story.append(Paragraph(title, styles["BrandTitle"]))
    if subtitle:
        story.append(Paragraph(subtitle, styles["BrandSub"]))
    story.append(HRFlowable(width="100%", thickness=1, color=BRASS, spaceAfter=12))
    story.append(Paragraph(f"Generated: {date.today().strftime('%d %B %Y')}", styles["BrandSub"]))


def generate_inventory_pdf(assets) -> BytesIO:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), topMargin=15*mm, bottomMargin=15*mm,
                            leftMargin=15*mm, rightMargin=15*mm)
    styles = _base_styles()
    story = []
    _header_section(story, styles, "Inventory Report", f"Total Assets: {len(assets)}")
    story.append(Spacer(1, 6*mm))

    headers = ["Asset Tag", "Name", "Category", "Department", "Location", "Status", "Purchase Date", "Cost (₹)", "Warranty Expiry"]
    data = [headers]
    for a in assets:
        data.append([
            a.asset_tag,
            a.name[:35],
            a.category,
            a.department.name if a.department else "—",
            (a.location or "—")[:25],
            a.status_label,
            a.purchase_date.strftime("%d/%m/%Y") if a.purchase_date else "—",
            f"₹{float(a.purchase_cost or 0):,.0f}",
            a.warranty_expiry.strftime("%d/%m/%Y") if a.warranty_expiry else "—",
        ])

    col_widths = [55, 90, 65, 70, 65, 60, 65, 55, 65]
    tbl = Table(data, colWidths=[w*mm for w in [20, 50, 32, 38, 35, 28, 28, 28, 30]])
    tbl.setStyle(_table_style())
    story.append(tbl)
    doc.build(story)
    buffer.seek(0)
    return buffer


def generate_maintenance_pdf(logs) -> BytesIO:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), topMargin=15*mm, bottomMargin=15*mm,
                            leftMargin=15*mm, rightMargin=15*mm)
    styles = _base_styles()
    story = []
    _header_section(story, styles, "Maintenance Report", f"Total Records: {len(logs)}")
    story.append(Spacer(1, 6*mm))

    headers = ["#", "Asset Tag", "Asset Name", "Issue", "Status", "Priority", "Requested", "Completed", "Actual Cost (₹)"]
    data = [headers]
    for i, log in enumerate(logs, 1):
        data.append([
            str(i),
            log.asset.asset_tag if log.asset else "—",
            (log.asset.name[:30] if log.asset else "—"),
            (log.issue_description or "")[:30],
            log.status.replace("_", " ").title(),
            log.priority.title() if log.priority else "—",
            log.request_date.strftime("%d/%m/%Y") if log.request_date else "—",
            log.completed_date.strftime("%d/%m/%Y") if log.completed_date else "—",
            f"₹{float(log.actual_cost or 0):,.0f}",
        ])

    tbl = Table(data, colWidths=[8*mm, 22*mm, 50*mm, 55*mm, 28*mm, 22*mm, 25*mm, 25*mm, 28*mm])
    tbl.setStyle(_table_style())
    story.append(tbl)
    doc.build(story)
    buffer.seek(0)
    return buffer


def generate_budget_pdf(estimates, departments) -> BytesIO:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=15*mm, bottomMargin=15*mm,
                            leftMargin=15*mm, rightMargin=15*mm)
    styles = _base_styles()
    story = []
    _header_section(story, styles, "Annual Budget Report", f"Fiscal Year {date.today().year}")
    story.append(Spacer(1, 6*mm))

    headers = ["Department", "Category", "Est. Maintenance (₹)", "Est. Replacement (₹)", "Total Est. (₹)", "Actual Spent (₹)", "Variance (₹)"]
    data = [headers]
    for e in estimates:
        total = float(e.estimated_maintenance_cost or 0) + float(e.estimated_replacement_cost or 0)
        actual = float(e.actual_spent or 0)
        variance = actual - total
        data.append([
            e.department.name if e.department else "—",
            e.category or "All",
            f"₹{float(e.estimated_maintenance_cost or 0):,.0f}",
            f"₹{float(e.estimated_replacement_cost or 0):,.0f}",
            f"₹{total:,.0f}",
            f"₹{actual:,.0f}",
            f"₹{variance:,.0f}",
        ])

    tbl = Table(data, colWidths=[45*mm, 30*mm, 35*mm, 35*mm, 30*mm, 30*mm, 30*mm])
    tbl.setStyle(_table_style())
    story.append(tbl)
    doc.build(story)
    buffer.seek(0)
    return buffer
