"""PDF export for party waybills (точковки)."""

import io
import os
from datetime import datetime
from pathlib import Path

from app.storage import DATA_DIR

# Fonts that ship with common desktop platforms and cover Cyrillic. The
# built-in Helvetica font cannot render Russian text, so it must be replaced
# with an embedded TrueType font.
_FONT_PAIRS = [
    (
        os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "arial.ttf"),
        os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "arialbd.ttf"),
    ),
    (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ),
    (
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ),
    (
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    ),
    ("/Library/Fonts/Arial.ttf", "/Library/Fonts/Arial Bold.ttf"),
]

_fonts = None


def _cyrillic_fonts():
    """Return (regular, bold) font names registered with ReportLab."""
    global _fonts
    if _fonts is not None:
        return _fonts
    regular, bold = "Helvetica", "Helvetica-Bold"
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.pdfdoc import PDFError
        from reportlab.pdfbase.ttfonts import TTFont
    except ImportError:
        _fonts = (regular, bold)
        return _fonts
    for regular_file, bold_file in _FONT_PAIRS:
        if not Path(regular_file).is_file():
            continue
        try:
            pdfmetrics.registerFont(TTFont("PartySans", regular_file))
            regular = "PartySans"
            if Path(bold_file).is_file():
                pdfmetrics.registerFont(TTFont("PartySans-Bold", bold_file))
                bold = "PartySans-Bold"
            else:
                bold = "PartySans"
            pdfmetrics.registerFontFamily(
                "PartySans", normal=regular, bold=bold, italic=regular,
                boldItalic=bold,
            )
        except (PDFError, OSError, ValueError):
            # A broken or unreadable font file must not stop the export: fall
            # back to the built-in Helvetica pair.
            regular, bold = "Helvetica", "Helvetica-Bold"
            continue
        break
    _fonts = (regular, bold)
    return _fonts


def _build_party_pdf(party, target):
    """Render the party waybill into ``target`` (a path or a binary stream)."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError as exc:
        raise RuntimeError("Для создания PDF требуется пакет reportlab.") from exc

    font_regular, font_bold = _cyrillic_fonts()
    styles = getSampleStyleSheet()
    normal = styles["Normal"]
    normal.fontName = font_regular
    title = styles["Title"]
    title.fontName = font_bold
    elements = [
        Paragraph(f"Точковка {party['name']}", title),
        Paragraph(
            f"{party['name']} · {datetime.fromisoformat(party['updated_at']):%d.%m.%Y}",
            normal,
        ),
        Spacer(1, 6 * mm),
    ]
    rows = [["Позиция", "Длина, м", "Шт", "Объём, м³"]]
    total = 0.0
    count = 0
    volume_digits = 3 if party["type"] == "ГОСТ" else 4
    for item in party.get("payload", []):
        if party["type"] == "Пиломатериал":
            position = f"{item.get('thickness_cm', 0):g}×{item.get('width_cm', 0):g}"
        else:
            position = f"Ø{item.get('diameter_cm', item.get('diameter', 0))} см"
        quantity = int(item.get("quantity", 0))
        volume = float(item.get("volume_m3", item.get("volume", 0)))
        rows.append([
            position, str(item.get("length_m", item.get("length", "—"))),
            quantity, f"{volume:.{volume_digits}f}",
        ])
        count += quantity
        total += volume
    rows.append(["Итого", "", count, f"{total:.{volume_digits}f}"])
    table = Table(rows, colWidths=[65 * mm, 35 * mm, 25 * mm, 40 * mm])
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.black),
        ("FONTNAME", (0, 0), (-1, -1), font_regular),
        ("FONTNAME", (0, 0), (-1, 0), font_bold),
        ("FONTNAME", (0, -1), (-1, -1), font_bold),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
    ]))
    elements.extend([
        table,
        Spacer(1, 10 * mm),
        Paragraph("Объём по ГОСТ 2708-75 (толщина верхнего торца без коры; "
                  "толщина и длина округлены по ГОСТ 2292-88)", normal),
        Paragraph("Средний диаметр 00,0 см", normal),
        Spacer(1, 16 * mm),
        Paragraph("Сдал ____________________                 Принял ____________________", normal),
        Spacer(1, 150 * mm),
        Paragraph("Рассчитано в приложении «Кубатура Экспресс». Документ справочный, "
                  "не является первичным учётным документом без подписи сторон.", normal),
    ])
    SimpleDocTemplate(target, pagesize=A4, rightMargin=18 * mm,
                      leftMargin=18 * mm, topMargin=16 * mm, bottomMargin=12 * mm).build(elements)


def create_party_pdf_bytes(party):
    """Render the waybill in memory and return its bytes.

    Web and mobile clients cannot read server-side files, so the PDF is handed
    over as bytes instead of a path.
    """
    buffer = io.BytesIO()
    _build_party_pdf(party, buffer)
    return buffer.getvalue()


def create_party_pdf(party):
    """Create a monochrome reference document and return its local path.

    ReportLab is an optional runtime dependency for desktop development; the
    application reports a friendly message if a platform build does not carry
    it yet.
    """
    path = Path(DATA_DIR) / f"точковка_{party['id']}.pdf"
    _build_party_pdf(party, str(path))
    return path
