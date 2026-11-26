"""PDF export for party waybills (точковки)."""

from datetime import datetime
from pathlib import Path

from app.storage import DATA_DIR


def create_party_pdf(party):
    """Create a monochrome reference document and return its local path.

    ReportLab is an optional runtime dependency for desktop development; the
    application reports a friendly message if a platform build does not carry
    it yet.
    """
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError as exc:
        raise RuntimeError("Для создания PDF требуется пакет reportlab.") from exc

    path = Path(DATA_DIR) / f"точковка_{party['id']}.pdf"
    styles = getSampleStyleSheet()
    normal = styles["Normal"]
    title = styles["Title"]
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
    for item in party.get("payload", []):
        if party["type"] == "Пиломатериал":
            position = f"{item.get('thickness_cm', 0):g}×{item.get('width_cm', 0):g}"
        else:
            position = f"Ø{item.get('diameter_cm', item.get('diameter', 0))} см"
        quantity = int(item.get("quantity", 0))
        volume = float(item.get("volume_m3", item.get("volume", 0)))
        rows.append([position, str(item.get("length_m", item.get("length", "—"))), quantity, f"{volume:.4f}"])
        count += quantity
        total += volume
    rows.append(["Итого", "", count, f"{total:.4f}"])
    table = Table(rows, colWidths=[65 * mm, 35 * mm, 25 * mm, 40 * mm])
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.black),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
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
    SimpleDocTemplate(str(path), pagesize=A4, rightMargin=18 * mm,
                      leftMargin=18 * mm, topMargin=16 * mm, bottomMargin=12 * mm).build(elements)
    return path
