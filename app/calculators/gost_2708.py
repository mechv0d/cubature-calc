from decimal import Decimal


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
    length_key = format(length_m.normalize(), "f")
    try:
        unit_volume = Decimal(str(table[diameter_key][length_key]))
    except KeyError as exc:
        raise ValueError("Для такого диаметра и длины нет значения в таблице.") from exc
    return unit_volume * quantity
