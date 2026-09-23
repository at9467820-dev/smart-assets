"""
QR Code Generation Utilities
- Single asset QR code
- Bulk printable PDF label sheet
"""
import os
import qrcode
from qrcode.image.pil import PilImage
from PIL import Image, ImageDraw, ImageFont
from flask import current_app, url_for
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.utils import ImageReader
from io import BytesIO


def generate_asset_qr(asset, base_url: str = "") -> str:
    """
    Generate a QR code PNG for an asset.
    Returns the relative path (from static/) to the saved QR image.
    """
    qr_folder = current_app.config["QR_FOLDER"]
    filename = f"qr_{asset.asset_tag}.png"
    filepath = os.path.join(qr_folder, filename)

    # The QR encodes the public URL to view the asset
    qr_url = f"{base_url}/assets/{asset.id}"

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(qr_url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="#12203D", back_color="white")

    # Add label below QR
    label_height = 40
    qr_img = img.get_image() if hasattr(img, "get_image") else img._img
    w, h = qr_img.size
    labeled = Image.new("RGB", (w, h + label_height), "white")
    labeled.paste(qr_img, (0, 0))
    draw = ImageDraw.Draw(labeled)
    try:
        font = ImageFont.truetype("arial.ttf", 18)
    except Exception:
        font = ImageFont.load_default()
    text = asset.asset_tag
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    draw.text(((w - text_w) // 2, h + 8), text, fill="#12203D", font=font)
    labeled.save(filepath, "PNG")

    return f"qrcodes/{filename}"


def generate_bulk_qr_pdf(assets, base_url: str = "") -> BytesIO:
    """
    Generate a printable A4 PDF sheet of QR code labels for a list of assets.
    Returns a BytesIO buffer containing the PDF.
    """
    buffer = BytesIO()
    c = rl_canvas.Canvas(buffer, pagesize=A4)
    page_w, page_h = A4

    cols = 3
    rows_per_page = 5
    label_w = page_w / cols
    label_h = page_h / rows_per_page
    margin = 5 * mm
    qr_size = label_w - 2 * margin

    for idx, asset in enumerate(assets):
        col = idx % cols
        row = (idx // cols) % rows_per_page
        page_idx = idx // (cols * rows_per_page)

        if idx > 0 and idx % (cols * rows_per_page) == 0:
            c.showPage()

        x = col * label_w + margin
        y = page_h - (row + 1) * label_h + margin

        # Generate in-memory QR
        qr_url = f"{base_url}/assets/{asset.id}"
        qr = qrcode.QRCode(version=1, box_size=8, border=2)
        qr.add_data(qr_url)
        qr.make(fit=True)
        qr_pil = img.get_image() if hasattr(img, "get_image") else getattr(img, "_img", img)
        qr_pil.save(img_buffer, "PNG")
        img_buffer.seek(0)

        img_size = min(qr_size, label_h - 20 * mm)
        c.drawImage(
            ImageReader(img_buffer),
            x, y + 12 * mm,
            width=img_size, height=img_size,
            preserveAspectRatio=True,
        )
        c.setFont("Helvetica-Bold", 9)
        c.drawCentredString(x + label_w / 2 - margin, y + 6 * mm, asset.asset_tag)
        c.setFont("Helvetica", 7)
        name = asset.name[:30] + "…" if len(asset.name) > 30 else asset.name
        c.drawCentredString(x + label_w / 2 - margin, y + 2 * mm, name)

        # Border
        c.rect(col * label_w, page_h - (row + 1) * label_h, label_w, label_h)

    c.save()
    buffer.seek(0)
    return buffer
