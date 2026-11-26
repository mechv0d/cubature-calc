"""Excel (XLSX) export for calculation summaries."""

import io
from pathlib import Path

from app.storage import DATA_DIR


def _openpyxl():
    """Import openpyxl lazily so the rest of the app works without it."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    except ImportError as exc:
        raise RuntimeError(
            "Для экспорта в Excel требуется пакет openpyxl."
        ) from exc
    return Workbook, Alignment, Border, Font, PatternFill, Side


def build_calculation_xlsx(calculation):
    """Build an XLSX workbook for a calculation and return its bytes.

    ``calculation`` contains already formatted summary data::

        {
            "number": 4,
            "title": "Расчет #4 (ГОСТ-75-Табл.1)",
            "date": "26.11.2026",
            "species": "сосна",
            "calc_type": "продажа",
            "counterparty": "ООО Лес",
            "counterparty_phone": "+7 900 000-00-00",
            "counterparty_email": "les@example.ru",
            "price_text": "1000.0 RUB.",
            "rows": [
                {"label": "14", "length": "6.0", "quantity": 1,
                 "volume": 0.123, "cost": None, "bold": False},
                {"label": "[12-17]", "length": "", "quantity": 1,
                 "volume": 0.123, "cost": 0.0, "bold": True},
            ],
            "total_quantity": 6,
            "total_volume": 5.358,
            "total_cost": 0.0,
        }
    """
    Workbook, Alignment, Border, Font, PatternFill, Side = _openpyxl()

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Расчет"

    thin = Side(style="thin", color="D5D9D8")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    bold = Font(bold=True)
    header_fill = PatternFill("solid", fgColor="F4F0E1")
    total_fill = PatternFill("solid", fgColor="FFF3CC")

    sheet.merge_cells("A1:E1")
    sheet["A1"] = calculation.get("title", "Расчет")
    sheet["A1"].font = Font(bold=True, size=14)
    sheet["A1"].alignment = Alignment(horizontal="center", vertical="center")
    sheet.row_dimensions[1].height = 24

    metadata = [
        ("Дата:", calculation.get("date", "")),
        ("Порода:", calculation.get("species", "")),
        ("Тип расчёта:", calculation.get("calc_type", "")),
        ("Контрагент:", calculation.get("counterparty", "")),
    ]
    if calculation.get("counterparty_phone"):
        metadata.append(("Телефон:", calculation["counterparty_phone"]))
    if calculation.get("counterparty_email"):
        metadata.append(("Email:", calculation["counterparty_email"]))
    metadata.append(("Цена 1 м³:", calculation.get("price_text", "")))

    for row_index, (label, value) in enumerate(metadata, start=2):
        label_cell = sheet.cell(row=row_index, column=1, value=label)
        label_cell.font = bold
        sheet.cell(row=row_index, column=2, value=value)

    header_row = len(metadata) + 3

    headers = (
        "Диаметр", "Длина, м", "Кол., шт.", "Объём, м³", "Стоимость, RUB",
    )
    for column, header in enumerate(headers, start=1):
        cell = sheet.cell(row=header_row, column=column, value=header)
        cell.font = bold
        cell.fill = header_fill
        cell.border = border
        cell.alignment = Alignment(
            horizontal="center", vertical="center", wrap_text=True,
        )

    row_index = header_row + 1
    for row in calculation.get("rows", []):
        values = (
            row.get("label", ""),
            row.get("length", ""),
            row.get("quantity", 0),
            row.get("volume", 0),
            row.get("cost"),
        )
        for column, value in enumerate(values, start=1):
            if column == 5 and value is None:
                value = "-"
            cell = sheet.cell(row=row_index, column=column, value=value)
            cell.border = border
            if row.get("bold"):
                cell.font = bold
            if column == 4:
                cell.number_format = "0.000"
            elif column == 5 and value != "-":
                cell.number_format = "0.00"
            if column in (2, 3, 4, 5):
                cell.alignment = Alignment(horizontal="right")
        row_index += 1

    total_values = (
        "Итого",
        "",
        calculation.get("total_quantity", 0),
        calculation.get("total_volume", 0),
        calculation.get("total_cost", 0),
    )
    for column, value in enumerate(total_values, start=1):
        cell = sheet.cell(row=row_index, column=column, value=value)
        cell.font = bold
        cell.fill = total_fill
        cell.border = border
        if column == 4:
            cell.number_format = "0.000"
        elif column == 5:
            cell.number_format = "0.00"
        if column in (2, 3, 4, 5):
            cell.alignment = Alignment(horizontal="right")

    for column, width in {
        "A": 22, "B": 12, "C": 11, "D": 14, "E": 18,
    }.items():
        sheet.column_dimensions[column].width = width

    sheet.freeze_panes = f"A{header_row + 1}"

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def create_calculation_xlsx_file(calculation):
    """Write the workbook to the app data directory and return its path."""
    number = calculation.get("number", "1")
    path = Path(DATA_DIR) / f"расчет_{number}.xlsx"
    path.write_bytes(build_calculation_xlsx(calculation))
    return path
