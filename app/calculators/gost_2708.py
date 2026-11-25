import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

DEFAULT_TABLE_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "gost_2708_table_1.json"
)


def load_gost_table(path=DEFAULT_TABLE_PATH) -> dict:
    """Load a verified GOST 2708-75 table from JSON."""
    with Path(path).open(encoding="utf-8") as source:
        return json.load(source)


def _as_decimal(value):
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _find_length_key(length_m: Decimal, diameter_row: dict) -> str:
    """Find a length key even if the table stores 6.0 while Decimal gives 6."""
    normalized = format(length_m.normalize(), "f")
    if normalized in diameter_row:
        return normalized
    if "." not in normalized and f"{normalized}.0" in diameter_row:
        return f"{normalized}.0"
    for key in diameter_row:
        if _as_decimal(key) == length_m:
            return key
    raise KeyError(normalized)


def calculate_gost_item(diameter_cm: int, length_m: Decimal, quantity: int, table: dict):
    """Calculate item volume using a verified imported GOST table.

    Expected table shape:
        {
          "diameter_cm": {
            "length_m": "unit_volume_m3"
          }
        }

    Values must come from a verified edition/table, not estimates.
    """
    diameter_key = str(diameter_cm)
    try:
        diameter_row = table[diameter_key]
        length_key = _find_length_key(length_m, diameter_row)
        unit_volume = Decimal(str(diameter_row[length_key]))
    except KeyError as exc:
        raise ValueError("Для такого диаметра и длины нет значения в таблице.") from exc
    return unit_volume * quantity
