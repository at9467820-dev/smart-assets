"""
AssetPulse — Parchi (Gate Pass & Material Issue Slip) PDF Generation Utilities
Generates professional printable and downloadable Issue Slips, Gate Passes, and Return Receipts.
"""
from io import BytesIO
from datetime import datetime
import qrcode
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable, Image as RLImage
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

# Brand Palette
PRIMARY = colors.HexColor("#091A17")
EMERALD = colors.HexColor("#10B981")
BRASS = colors.HexColor("#D4AF37")
NAVY = colors.HexColor("#12203D")
LIGHT_BG = colors.HexColor("#F8FAFC")
BORDER_COLOR = colors.HexColor("#CBD5E1")
TEXT_DARK = colors.HexColor("#0F172A")
TEXT_MUTED = colors.HexColor("#64748B")
WHITE = colors.white


def _create_qr_image(data_text: str, size_mm: float = 30.0):
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=6,
        border=1,
    )
    qr.add_data(data_text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#091A17", back_color="white")
    buf = BytesIO()
    qr_pil = img.get_image() if hasattr(img, "get_image") else getattr(img, "_img", img)
    qr_pil.save(buf, "PNG")
    buf.seek(0)
    return RLImage(buf, width=size_mm * mm, height=size_mm * mm)


def generate_issue_parchi_pdf(issue, base_url: str = "") -> BytesIO:
    """
    Generate an official Material Issue Slip / Gate Pass ('Parchi') as an A4 PDF.
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ParchiTitle",
        fontName="Helvetica-Bold",
        fontSize=15,
        textColor=PRIMARY,
        alignment=TA_CENTER,
        spaceAfter=2,
    )
    sub_style = ParagraphStyle(
        "ParchiSub",
        fontName="Helvetica-Bold",
        fontSize=11,
        textColor=BRASS,
        alignment=TA_CENTER,
        spaceAfter=4,
    )
    slip_no_style = ParagraphStyle(
        "SlipNo",
        fontName="Helvetica-Bold",
        fontSize=10,
        textColor=TEXT_DARK,
        alignment=TA_RIGHT,
    )
    lbl_style = ParagraphStyle(
        "LabelStyle",
        fontName="Helvetica-Bold",
        fontSize=8.5,
        textColor=TEXT_MUTED,
    )
    val_style = ParagraphStyle(
        "ValueStyle",
        fontName="Helvetica",
        fontSize=9,
        textColor=TEXT_DARK,
    )
    val_bold = ParagraphStyle(
        "ValueBold",
        fontName="Helvetica-Bold",
        fontSize=9.5,
        textColor=PRIMARY,
    )
    terms_style = ParagraphStyle(
        "TermsStyle",
        fontName="Helvetica",
        fontSize=7.5,
        textColor=TEXT_MUTED,
        leading=10,
    )

    story = []

    # 1. Header Box with Institution branding & Slip No
    header_data = [
        [
            Paragraph("<b>ASSETPULSE INSTITUTIONAL REGISTRY</b><br/><font size=8 color='#64748B'>Smart Asset Management System (SAMS) • Gate Pass & Material Issue Voucher</font>", ParagraphStyle("HdrLeft", fontName="Helvetica", fontSize=10, textColor=PRIMARY)),
            Paragraph(f"<b>SLIP NO:</b> <font color='#10B981'>{issue.slip_number}</font><br/><font size=7 color='#64748B'>TYPE: {issue.gate_pass_type.upper()}</font>", slip_no_style),
        ]
    ]
    hdr_table = Table(header_data, colWidths=[120 * mm, 62 * mm])
    hdr_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(hdr_table)
    story.append(HRFlowable(width="100%", thickness=1.5, color=PRIMARY, spaceAfter=6, spaceBefore=4))

    # Title Banner
    banner_data = [[Paragraph("OFFICIAL MATERIAL ISSUE SLIP / GATE PASS (PARCHI)", title_style)]]
    banner_tbl = Table(banner_data, colWidths=[182 * mm])
    banner_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BG),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
    ]))
    story.append(banner_tbl)
    story.append(Spacer(1, 4 * mm))

    # 2. Main Details: 2-column layout (Left: Issue & Receiver Info, Right: Asset Info & QR)
    qr_url = f"{base_url}/issues/{issue.id}" if base_url else f"https://assetpulse.internal/issues/{issue.id}"
    qr_img = _create_qr_image(qr_url, size_mm=26)

    issue_dt_str = issue.issue_date.strftime("%d %b %Y, %I:%M %p") if issue.issue_date else "N/A"
    return_dt_str = issue.expected_return_date.strftime("%d %b %Y, %I:%M %p") if issue.expected_return_date else "Non-Returnable / Consumable"

    # Issuer & Receiver Table
    people_data = [
        [Paragraph("ISSUE & AUTHORIZATION DETAILS", ParagraphStyle("SecHdr1", fontName="Helvetica-Bold", fontSize=8.5, textColor=WHITE)), ""],
        [Paragraph("Issue Date & Time:", lbl_style), Paragraph(issue_dt_str, val_bold)],
        [Paragraph("Authorized Issuer (Issued By):", lbl_style), Paragraph(f"<b>{issue.issuer_name or (issue.issued_by.full_name if issue.issued_by else 'Admin')}</b> ({issue.issued_by.role.title() if issue.issued_by else 'Staff'})", val_style)],
        [Paragraph("Issuer Department:", lbl_style), Paragraph(issue.issued_by.department.name if (issue.issued_by and issue.issued_by.department) else "Central Administration", val_style)],
        [Paragraph("Expected Return Due:", lbl_style), Paragraph(f"<font color='#B98A2E'><b>{return_dt_str}</b></font>", val_bold)],
        [Paragraph("RECIPIENT / HOLDER DETAILS", ParagraphStyle("SecHdr2", fontName="Helvetica-Bold", fontSize=8.5, textColor=WHITE)), ""],
        [Paragraph("Issued To (Recipient Name):", lbl_style), Paragraph(f"<b>{issue.issued_to_name}</b>", val_bold)],
        [Paragraph("ID / Roll / Employee No:", lbl_style), Paragraph(issue.issued_to_id_number or "N/A", val_style)],
        [Paragraph("Recipient Department:", lbl_style), Paragraph(issue.issued_to_dept or "N/A", val_style)],
        [Paragraph("Contact Number:", lbl_style), Paragraph(issue.issued_to_phone or "N/A", val_style)],
        [Paragraph("Email Address:", lbl_style), Paragraph(issue.issued_to_email or "N/A", val_style)],
        [Paragraph("Purpose of Issue:", lbl_style), Paragraph(f"<b>{issue.purpose}</b>", val_style)],
    ]
    people_tbl = Table(people_data, colWidths=[55 * mm, 60 * mm])
    people_tbl.setStyle(TableStyle([
        ("SPAN", (0, 0), (1, 0)),
        ("BACKGROUND", (0, 0), (1, 0), PRIMARY),
        ("SPAN", (0, 5), (1, 5)),
        ("BACKGROUND", (0, 5), (1, 5), NAVY),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ("BACKGROUND", (0, 1), (0, 4), LIGHT_BG),
        ("BACKGROUND", (0, 6), (0, -1), LIGHT_BG),
    ]))

    # Asset Table + QR Block
    asset = issue.asset
    asset_data = [
        [Paragraph("ASSET & MATERIAL SPECIFICATIONS", ParagraphStyle("SecHdr3", fontName="Helvetica-Bold", fontSize=8.5, textColor=WHITE)), ""],
        [Paragraph("Asset Tag:", lbl_style), Paragraph(f"<b>{asset.asset_tag}</b>", val_bold)],
        [Paragraph("Item Name:", lbl_style), Paragraph(asset.name, val_style)],
        [Paragraph("Category:", lbl_style), Paragraph(asset.category, val_style)],
        [Paragraph("Serial Number:", lbl_style), Paragraph(asset.serial_number or "N/A", val_style)],
        [Paragraph("Model / Brand:", lbl_style), Paragraph(f"{asset.manufacturer or ''} {asset.model_number or ''}".strip() or "N/A", val_style)],
        [Paragraph("Home Department:", lbl_style), Paragraph(asset.department.name if asset.department else "N/A", val_style)],
        [Paragraph("Location / Lab:", lbl_style), Paragraph(asset.location or "N/A", val_style)],
        [Paragraph("Condition on Issue:", lbl_style), Paragraph(f"<font color='#3F7D58'><b>{issue.issue_condition or 'Good'}</b></font>", val_style)],
        [Paragraph("Issue Remarks / Note:", lbl_style), Paragraph(issue.remarks_on_issue or "Standard issue without restrictions.", val_style)],
        [Paragraph("Scan to Verify & Track:", lbl_style), qr_img],
    ]
    asset_tbl = Table(asset_data, colWidths=[32 * mm, 33 * mm])
    asset_tbl.setStyle(TableStyle([
        ("SPAN", (0, 0), (1, 0)),
        ("BACKGROUND", (0, 0), (1, 0), PRIMARY),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ("BACKGROUND", (0, 1), (0, -1), LIGHT_BG),
        ("ALIGN", (1, 10), (1, 10), "CENTER"),
    ]))

    # Combine side-by-side
    two_col = Table([[people_tbl, asset_tbl]], colWidths=[115 * mm, 67 * mm])
    two_col.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(two_col)
    story.append(Spacer(1, 4 * mm))

    # 3. Terms & Custodian Declaration
    terms_text = (
        "<b>TERMS & CUSTODY AGREEMENT:</b> 1. The recipient acknowledges receipt of the material/asset in good condition as described above. "
        "2. The recipient is solely responsible for safe custody and proper handling. In case of physical damage, loss, or unauthorized transfer, the recipient will be liable. "
        "3. The asset must be returned on or before the Expected Return Date. 4. Security personnel are authorized to check this gate pass at checkpoints."
    )
    terms_tbl = Table([[Paragraph(terms_text, terms_style)]], colWidths=[182 * mm])
    terms_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BG),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(terms_tbl)
    story.append(Spacer(1, 8 * mm))

    # 4. Triple Signature Boxes (Issuer, Recipient, Gate Security)
    sig_data = [
        [
            Paragraph("<b>ISSUING AUTHORITY</b><br/><br/><br/>___________________________<br/><font size=7 color='#64748B'>Signature & Official Seal</font>", ParagraphStyle("Sig1", fontName="Helvetica", fontSize=8, alignment=TA_CENTER)),
            Paragraph("<b>RECEIVER / BEARER</b><br/><br/><br/>___________________________<br/><font size=7 color='#64748B'>Recipient Signature & Date</font>", ParagraphStyle("Sig2", fontName="Helvetica", fontSize=8, alignment=TA_CENTER)),
            Paragraph("<b>SECURITY CHECKPOINT</b><br/><br/><br/>___________________________<br/><font size=7 color='#64748B'>Gate Out Stamp & Initials</font>", ParagraphStyle("Sig3", fontName="Helvetica", fontSize=8, alignment=TA_CENTER)),
        ]
    ]
    sig_tbl = Table(sig_data, colWidths=[60 * mm, 60 * mm, 62 * mm])
    sig_tbl.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(sig_tbl)

    # Footer note
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(f"<font size=7 color='#94A3B8'>AssetPulse SAMS Automated Gate Pass System • Slip ID: {issue.slip_number} • Generated on {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}</font>", ParagraphStyle("Ftr", fontName="Helvetica", fontSize=7, alignment=TA_CENTER)))

    doc.build(story)
    buffer.seek(0)
    return buffer


def generate_return_parchi_pdf(issue, base_url: str = "") -> BytesIO:
    """
    Generate an official Return Clearance Slip & Voucher ('Return Parchi') as an A4 PDF.
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ParchiTitle",
        fontName="Helvetica-Bold",
        fontSize=15,
        textColor=PRIMARY,
        alignment=TA_CENTER,
        spaceAfter=2,
    )
    slip_no_style = ParagraphStyle(
        "SlipNo",
        fontName="Helvetica-Bold",
        fontSize=10,
        textColor=TEXT_DARK,
        alignment=TA_RIGHT,
    )
    lbl_style = ParagraphStyle(
        "LabelStyle",
        fontName="Helvetica-Bold",
        fontSize=8.5,
        textColor=TEXT_MUTED,
    )
    val_style = ParagraphStyle(
        "ValueStyle",
        fontName="Helvetica",
        fontSize=9,
        textColor=TEXT_DARK,
    )
    val_bold = ParagraphStyle(
        "ValueBold",
        fontName="Helvetica-Bold",
        fontSize=9.5,
        textColor=PRIMARY,
    )

    story = []

    # Header
    header_data = [
        [
            Paragraph("<b>ASSETPULSE INSTITUTIONAL REGISTRY</b><br/><font size=8 color='#64748B'>Smart Asset Management System (SAMS) • Material Return & Clearance Voucher</font>", ParagraphStyle("HdrLeft", fontName="Helvetica", fontSize=10, textColor=PRIMARY)),
            Paragraph(f"<b>SLIP NO:</b> <font color='#10B981'>{issue.slip_number}</font><br/><font size=7 color='#3F7D58'>STATUS: RETURNED & VERIFIED</font>", slip_no_style),
        ]
    ]
    hdr_table = Table(header_data, colWidths=[120 * mm, 62 * mm])
    hdr_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(hdr_table)
    story.append(HRFlowable(width="100%", thickness=1.5, color=PRIMARY, spaceAfter=6, spaceBefore=4))

    # Banner
    banner_data = [[Paragraph("OFFICIAL MATERIAL RETURN & CLEARANCE RECEIPT (RETURN PARCHI)", title_style)]]
    banner_tbl = Table(banner_data, colWidths=[182 * mm])
    banner_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BG),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
    ]))
    story.append(banner_tbl)
    story.append(Spacer(1, 4 * mm))

    # Return summary table
    ret_dt_str = issue.actual_return_date.strftime("%d %b %Y, %I:%M %p") if issue.actual_return_date else datetime.now().strftime("%d %b %Y, %I:%M %p")
    rec_by_name = issue.received_by.full_name if issue.received_by else "Authorized Staff"

    summary_data = [
        [Paragraph("MATERIAL RETURN & CLEARANCE AUDIT", ParagraphStyle("SecHdrR", fontName="Helvetica-Bold", fontSize=8.5, textColor=WHITE)), ""],
        [Paragraph("Asset Tag & Name:", lbl_style), Paragraph(f"<b>{issue.asset.asset_tag}</b> — {issue.asset.name}", val_bold)],
        [Paragraph("Returned By (Bearer):", lbl_style), Paragraph(f"<b>{issue.issued_to_name}</b> ({issue.issued_to_id_number or 'N/A'}, {issue.issued_to_dept or 'N/A'})", val_style)],
        [Paragraph("Issue Date & Time:", lbl_style), Paragraph(issue.issue_date.strftime("%d %b %Y, %I:%M %p"), val_style)],
        [Paragraph("Return Date & Time:", lbl_style), Paragraph(f"<b>{ret_dt_str}</b>", val_bold)],
        [Paragraph("Verified & Received By:", lbl_style), Paragraph(f"<b>{rec_by_name}</b>", val_style)],
        [Paragraph("Condition on Return:", lbl_style), Paragraph(f"<b>{issue.return_condition or 'Good / Functional'}</b>", val_bold)],
        [Paragraph("Fine / Damage Penalty:", lbl_style), Paragraph(f"₹{float(issue.fine_amount or 0):,.2f}", val_style)],
        [Paragraph("Return Remarks & Notes:", lbl_style), Paragraph(issue.remarks_on_return or "Asset inspected and accepted back into inventory.", val_style)],
    ]
    sum_tbl = Table(summary_data, colWidths=[55 * mm, 127 * mm])
    sum_tbl.setStyle(TableStyle([
        ("SPAN", (0, 0), (1, 0)),
        ("BACKGROUND", (0, 0), (1, 0), PRIMARY),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ("BACKGROUND", (0, 1), (0, -1), LIGHT_BG),
    ]))
    story.append(sum_tbl)
    story.append(Spacer(1, 10 * mm))

    # Dual Signatures
    sig_data = [
        [
            Paragraph("<b>RETURNING BEARER</b><br/><br/><br/>___________________________<br/><font size=7 color='#64748B'>Signature of Recipient</font>", ParagraphStyle("SigR1", fontName="Helvetica", fontSize=8, alignment=TA_CENTER)),
            Paragraph("<b>INVENTORY CLEARANCE OFFICER</b><br/><br/><br/>___________________________<br/><font size=7 color='#64748B'>Authorized Signature & Seal</font>", ParagraphStyle("SigR2", fontName="Helvetica", fontSize=8, alignment=TA_CENTER)),
        ]
    ]
    sig_tbl = Table(sig_data, colWidths=[90 * mm, 92 * mm])
    sig_tbl.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(sig_tbl)

    doc.build(story)
    buffer.seek(0)
    return buffer
