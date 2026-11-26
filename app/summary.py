"""Shared «Итоги» screen for calculations (ГОСТ and оцилиндровка).

The summary tab, its totals panel, the action buttons (info / send / download /
save) and the calculation settings dialog are identical for every calculation
screen, so they live here and are reused by the screens themselves.
"""

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from itertools import pairwise
from pathlib import Path

import flet as ft

from app.excel_export import build_calculation_xlsx
from app.storage import DATA_DIR, list_counterparties, save_counterparty

GREEN = "#176B4A"
ORANGE = "#E89A4E"
TEXT = "#62666A"

SPECIES_OPTIONS = ("береза", "сосна", "осина", "дуб", "ель", "н/д")
CALC_TYPE_OPTIONS = (
    "продажа", "производство", "инвентаризация", "перемещение", "переработка",
)
DIAMETER_FILTER_OPTIONS = (
    ("all", "Все"), ("even", "Четные"), ("odd", "Нечетные"),
)
DEFAULT_PRICE_RANGES = (
    {"from": 3, "to": 11, "price": "0"},
    {"from": 12, "to": 17, "price": "0"},
    {"from": 18, "to": 120, "price": "0"},
)

COLUMN_WIDTHS = {"length": 52, "quantity": 38, "volume": 68, "cost": 78}

#: Высота полосы вкладок «Таблица» / «Итоги» и кнопок на ней.
TAB_BAR_HEIGHT = 46


def calc_tab_style(green, active):
    """Стиль вкладки расчётного экрана (без скруглений, во всю ширину)."""
    return ft.ButtonStyle(
        bgcolor=green,
        color="white" if active else "#B8D4C8",
        shape=ft.RoundedRectangleBorder(radius=0),
        padding=ft.Padding.symmetric(vertical=8),
    )


def calc_tab_bar(green, tabs):
    """Зелёная полоса с вкладками.

    Material-кнопки не закрашивают всю высоту, из-за чего под аппбаром
    появлялась светлая полоска. Фон полосы закрашивается отдельным
    контейнером, поэтому щелей между аппбаром и вкладками нет.
    """
    return ft.Container(
        bgcolor=green,
        height=TAB_BAR_HEIGHT,
        content=ft.Row(controls=list(tabs), spacing=0, tight=True),
    )


def normalize_price_ranges(ranges):
    """Return a validated, sorted copy of price ranges.

    Drafts and older app versions may contain incomplete ranges, so malformed
    entries are skipped instead of breaking the whole calculation screen.
    """
    result = []
    for item in ranges or []:
        try:
            start = int(item.get("from"))
            end = int(item.get("to"))
            price = Decimal(str(item.get("price", 0)))
        except (AttributeError, InvalidOperation, TypeError, ValueError):
            continue
        if start > end:
            start, end = end, start
        if price < 0:
            price = Decimal(0)
        result.append({
            "from": start,
            "to": end,
            "price": format(price.normalize(), "f"),
        })
    result.sort(key=lambda entry: (entry["from"], entry["to"]))
    return result


def default_settings():
    return {
        "ranges": [dict(item) for item in DEFAULT_PRICE_RANGES],
        "diameter_filter": "all",
        "species": "н/д",
        "calc_type": "продажа",
        "counterparty": {},
    }


def load_settings(saved):
    """Normalize settings restored from a draft, filling missing values."""
    settings = default_settings()
    if not isinstance(saved, dict):
        return settings
    ranges = normalize_price_ranges(
        saved.get("ranges") or DEFAULT_PRICE_RANGES
    )
    if ranges:
        settings["ranges"] = ranges
    filter_value = saved.get("diameter_filter", "all")
    if filter_value in {key for key, _ in DIAMETER_FILTER_OPTIONS}:
        settings["diameter_filter"] = filter_value
    if saved.get("species") in SPECIES_OPTIONS:
        settings["species"] = saved["species"]
    if saved.get("calc_type") in CALC_TYPE_OPTIONS:
        settings["calc_type"] = saved["calc_type"]
    counterparty = saved.get("counterparty")
    if isinstance(counterparty, dict):
        settings["counterparty"] = dict(counterparty)
    return settings


def price_for_diameter(settings, diameter):
    """Return ``(price, range)`` for a diameter, or ``(None, None)``."""
    for price_range in settings["ranges"]:
        if price_range["from"] <= diameter <= price_range["to"]:
            return Decimal(price_range["price"]), price_range
    return None, None


def info_price_text(settings):
    prices = [
        Decimal(price_range["price"]) for price_range in settings["ranges"]
    ]
    if not prices:
        return "0.0 RUB."
    unique = sorted(set(prices))
    if len(unique) == 1:
        return f"{unique[0]:.1f} RUB."
    return f"от {unique[0]:.1f} до {unique[-1]:.1f} RUB."


def format_length(value):
    text = f"{value:g}"
    return f"{text}.0" if "." not in text else text


def format_volume(value, digits=3):
    quantum = Decimal(1).scaleb(-digits)
    return f"{Decimal(value).quantize(quantum, rounding=ROUND_HALF_UP):.{digits}f}"


def format_money(value):
    return f"{value:.2f}"


def ask_quantity(page, label, current, on_save, minimum=0, maximum=1000):
    """Ask for a log quantity with a focused numeric field.

    ``label`` is the position description shown in the title (for example
    ``Ø30 6м``). ``on_save`` receives the validated quantity.
    """
    quantity_field = ft.TextField(
        label="Количество, шт",
        value=str(current),
        autofocus=True,
        keyboard_type=ft.KeyboardType.NUMBER,
        input_filter=ft.NumbersOnlyInputFilter(),
        text_align=ft.TextAlign.RIGHT,
    )
    error = ft.Text("", size=12, color="#B3261E", visible=False)

    def save(_):
        raw = str(quantity_field.value or "").strip()
        try:
            quantity = int(raw)
        except (TypeError, ValueError):
            quantity = None
        if quantity is None or not minimum <= quantity <= maximum:
            error.value = (
                f"Введите целое число от {minimum} до {maximum}."
            )
            error.visible = True
            page.update()
            return
        on_save(quantity)
        page.pop_dialog()
        page.update()

    page.show_dialog(ft.AlertDialog(
        modal=True,
        title=ft.Text(
            f'Выберите количество {label}', size=18,
            weight=ft.FontWeight.W_600,
        ),
        content=ft.Column(
            tight=True, spacing=10,
            controls=[quantity_field, error],
        ),
        actions=[
            ft.TextButton(
                "Отмена", on_click=lambda _: page.pop_dialog(),
            ),
            ft.FilledButton(
                "Сохранить", on_click=save,
                style=ft.ButtonStyle(bgcolor=GREEN, color="white"),
            ),
        ],
    ))


def group_items(items, ranges):
    """Group items by length and then by price range.

    Rows of different lengths must not be mixed in one range subtotal, so
    each ``(length, range)`` pair becomes its own group. Items that do not
    fall into any range are returned as leftovers.
    """
    items_sorted = sorted(
        items, key=lambda item: (item["length"], item["diameter"])
    )
    lengths = sorted({item["length"] for item in items_sorted})
    groups = []
    used = set()
    for length in lengths:
        length_items = [
            item for item in items_sorted if item["length"] == length
        ]
        for price_range in ranges:
            group = [
                item for item in length_items
                if price_range["from"] <= item["diameter"] <= price_range["to"]
                and id(item) not in used
            ]
            if not group:
                continue
            used.update(id(item) for item in group)
            groups.append((price_range, group))
    leftovers = [item for item in items_sorted if id(item) not in used]
    return groups, leftovers


def summary_cell(
    value, column=None, expand=False, bold=False,
    color=TEXT, size=14, align=ft.Alignment.CENTER_LEFT,
):
    return ft.Container(
        width=COLUMN_WIDTHS.get(column), expand=expand, alignment=align,
        padding=ft.Padding.symmetric(horizontal=3, vertical=7),
        content=ft.Text(
            str(value), size=size, color=color, no_wrap=True,
            weight=ft.FontWeight.BOLD if bold else None,
        ),
    )


def summary_row(values, bold=False, bgcolor=None, size=14):
    """Build one table row from a sequence of ``(column, value)`` pairs."""
    cells = []
    for column, value in values:
        cells.append(summary_cell(
            value, column=None if column == "diameter" else column,
            expand=column == "diameter", bold=bold, size=size,
            color="#1B211C" if bold else TEXT,
            align=(
                ft.Alignment.CENTER_LEFT if column == "diameter"
                else ft.Alignment.CENTER_RIGHT
            ),
        ))
    return ft.Container(
        bgcolor=bgcolor,
        border=ft.Border(bottom=ft.BorderSide(1, "#ECEFF0")),
        content=ft.Row(controls=cells),
    )


def build_summary_table(groups, leftovers, digits=3, empty_text=None):
    header = ft.Container(
        bgcolor="#F4F0E1",
        content=ft.Row(controls=[
            summary_cell("диаметр", expand=True, bold=True,
                         color="#1B211C", size=12),
            summary_cell("длина", column="length", bold=True,
                         color="#1B211C", size=12,
                         align=ft.Alignment.CENTER_RIGHT),
            summary_cell("кол.", column="quantity", bold=True,
                         color="#1B211C", size=12,
                         align=ft.Alignment.CENTER_RIGHT),
            summary_cell("объем", column="volume", bold=True,
                         color="#1B211C", size=12,
                         align=ft.Alignment.CENTER_RIGHT),
            summary_cell("стоимос...", column="cost", bold=True,
                         color="#1B211C", size=12,
                         align=ft.Alignment.CENTER_RIGHT),
        ]),
    )
    rows = [header]
    for index, (price_range, group) in enumerate(groups):
        if index:
            rows.append(ft.Container(height=10, bgcolor="#FFFFFF"))
        range_price = Decimal(price_range["price"])
        for item in group:
            rows.append(summary_row([
                ("diameter", item["diameter"]),
                ("length", format_length(item["length"])),
                ("quantity", item["quantity"]),
                ("volume", item["display_volume"]),
                ("cost", format_money(item["volume"] * range_price)),
            ]))
        group_volume = sum((item["volume"] for item in group), Decimal(0))
        group_cost = group_volume * range_price
        rows.append(summary_row([
            ("diameter", f"[{price_range['from']}-{price_range['to']}]"),
            ("length", ""),
            ("quantity", sum(item["quantity"] for item in group)),
            ("volume", format_volume(group_volume, digits)),
            ("cost", format_money(group_cost)),
        ], bold=True, bgcolor="#FBFBF8", size=15))
    for item in leftovers:
        rows.append(summary_row([
            ("diameter", item["diameter"]),
            ("length", format_length(item["length"])),
            ("quantity", item["quantity"]),
            ("volume", item["display_volume"]),
            ("cost", "-"),
        ]))
    if empty_text:
        rows.append(ft.Container(
            padding=16,
            content=ft.Text(empty_text, color=TEXT),
        ))
    return ft.Container(
        bgcolor="#FFFFFF",
        border=ft.Border.all(1, "#E4E8E4"),
        border_radius=12,
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        content=ft.Column(spacing=0, controls=rows),
    )


def build_totals_panel(volume_total, money_total, digits=3):
    return ft.Container(
        bgcolor="#FFFFFF",
        border=ft.Border.all(1, "#E4E8E4"),
        border_radius=14,
        padding=ft.Padding.symmetric(horizontal=12, vertical=10),
        content=ft.Row(
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Column(spacing=2, expand=True, controls=[
                    ft.Text("Итоговая кубатура", size=14, color=TEXT),
                    ft.Text(
                        f"{format_volume(volume_total, digits)} м³",
                        size=28, color=ORANGE,
                        weight=ft.FontWeight.BOLD,
                    ),
                ]),
                ft.Container(width=1, height=58, bgcolor="#E4E8E4"),
                ft.Column(
                    spacing=2, expand=True,
                    horizontal_alignment=ft.CrossAxisAlignment.END,
                    controls=[
                        ft.Text(
                            "Общая стоимость", size=14, color=TEXT,
                            text_align=ft.TextAlign.RIGHT,
                        ),
                        ft.Text(
                            f"{format_money(money_total)} RUB.",
                            size=22, color="#1B211C",
                            weight=ft.FontWeight.BOLD,
                        ),
                    ],
                ),
            ],
        ),
    )


class CalculationSummary:
    """Summary tab, totals and actions shared by all calculation screens.

    ``get_items`` must return a list of dicts with ``diameter`` (int),
    ``length`` (float), ``quantity`` (int), ``volume`` (Decimal) and
    ``display_volume`` (already formatted string).
    """

    def __init__(
        self,
        page,
        *,
        settings,
        number,
        title,
        get_items,
        digits=3,
        on_save=None,
        on_settings_changed=None,
        on_filter_changed=None,
        empty_text="Добавленных брёвен пока нет.",
        excel_note="Excel-таблица · ГОСТ 2708-75",
    ):
        self.page = page
        self.settings = settings
        self.number = number
        self.title = title
        self.get_items = get_items
        self.digits = digits
        self.on_save = on_save
        self.on_settings_changed = on_settings_changed
        self.on_filter_changed = on_filter_changed
        self.empty_text = empty_text
        self.excel_note = excel_note
        self._picker = None
        self._share = None
        self.view = ft.Column(
            spacing=12, expand=True, scroll=ft.ScrollMode.AUTO,
        )
        self.totals = ft.Container(
            visible=False,
            padding=ft.Padding.symmetric(horizontal=8, vertical=4),
        )
        self.actions = self._build_actions()

    # ---------------------------------------------------------------- data

    def items(self):
        return list(self.get_items())

    def total_volume(self, items=None):
        items = self.items() if items is None else items
        return sum((item["volume"] for item in items), Decimal(0))

    def total_cost(self, items=None):
        items = self.items() if items is None else items
        total = Decimal(0)
        for item in items:
            price, _ = price_for_diameter(self.settings, item["diameter"])
            if price is not None:
                total += item["volume"] * price
        return total

    def refresh(self):
        items = self.items()
        groups, leftovers = group_items(items, self.settings["ranges"])
        counterparty_name = (
            (self.settings["counterparty"] or {}).get("name") or "н/д"
        )
        self.view.controls = [
            ft.Row(
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text(
                        "Сводная таблица:", size=16,
                        weight=ft.FontWeight.W_600, expand=True,
                    ),
                    ft.Text(
                        datetime.now().strftime("%d.%m.%Y"),
                        size=14, color=TEXT,
                    ),
                ],
            ),
            ft.Text(
                f"Порода: {self.settings['species']} · "
                f"{self.settings['calc_type'].capitalize()} · "
                f"Контрагент: {counterparty_name}",
                size=12, color=TEXT,
            ),
            build_summary_table(
                groups, leftovers, self.digits,
                empty_text=None if items else self.empty_text,
            ),
        ]
        self.totals.content = build_totals_panel(
            self.total_volume(items), self.total_cost(items), self.digits,
        )

    # ------------------------------------------------------------- actions

    def _build_actions(self):
        action_style = ft.ButtonStyle(
            color="#1B211C",
            side=ft.BorderSide(1, "#D5D9D8"),
            shape=ft.RoundedRectangleBorder(radius=12),
            icon_color=GREEN,
            padding=ft.Padding.symmetric(horizontal=6, vertical=4),
        )
        return ft.Container(
            padding=ft.Padding.symmetric(horizontal=8, vertical=7),
            content=ft.Column(spacing=8, controls=[
                ft.Row(spacing=8, controls=[
                    ft.OutlinedButton(
                        content=ft.Icon(ft.Icons.INFO, color=GREEN, size=22),
                        width=52, height=52,
                        on_click=self.show_info,
                        style=action_style,
                    ),
                    ft.OutlinedButton(
                        "Отправить", icon=ft.Icons.SHARE,
                        expand=True, height=52,
                        on_click=self.show_send,
                        style=action_style,
                    ),
                    ft.OutlinedButton(
                        "Скачать", icon=ft.Icons.DOWNLOAD,
                        expand=True, height=52,
                        on_click=self.download_xlsx,
                        style=action_style,
                    ),
                ]),
                ft.Row(controls=[
                    ft.FilledButton(
                        content=ft.Row(
                            tight=True,
                            alignment=ft.MainAxisAlignment.CENTER,
                            controls=[
                                ft.Icon(ft.Icons.SAVE, color="white"),
                                ft.Text("Сохранить расчёт", color="white",
                                        weight=ft.FontWeight.BOLD),
                            ],
                        ),
                        expand=True,
                        height=58,
                        on_click=self._save_clicked,
                        style=ft.ButtonStyle(
                            bgcolor="#E77C3B", color="white",
                            shape=ft.RoundedRectangleBorder(radius=14),
                        ),
                    ),
                ]),
            ]),
        )

    def _save_clicked(self, event):
        if self.on_save:
            self.on_save(event)

    # ------------------------------------------------------------- export

    def export_calculation(self):
        items = self.items()
        groups, leftovers = group_items(items, self.settings["ranges"])
        rows = []
        for price_range, group in groups:
            range_price = Decimal(price_range["price"])
            for item in group:
                rows.append({
                    "label": str(item["diameter"]),
                    "length": format_length(item["length"]),
                    "quantity": item["quantity"],
                    "volume": float(item["volume"]),
                    "cost": float(item["volume"] * range_price),
                    "bold": False,
                })
            group_volume = sum((item["volume"] for item in group), Decimal(0))
            rows.append({
                "label": f"[{price_range['from']}-{price_range['to']}]",
                "length": (
                    format_length(group[0]["length"]) if group else ""
                ),
                "quantity": sum(item["quantity"] for item in group),
                "volume": float(group_volume),
                "cost": float(group_volume * range_price),
                "bold": True,
            })
        for item in leftovers:
            rows.append({
                "label": str(item["diameter"]),
                "length": format_length(item["length"]),
                "quantity": item["quantity"],
                "volume": float(item["volume"]),
                "cost": None,
                "bold": False,
            })
        counterparty = self.settings["counterparty"] or {}
        return {
            "number": self.number,
            "title": self.title,
            "date": datetime.now().strftime("%d.%m.%Y"),
            "species": self.settings["species"],
            "calc_type": self.settings["calc_type"],
            "counterparty": counterparty.get("name") or "н/д",
            "counterparty_phone": counterparty.get("phone") or "",
            "counterparty_email": counterparty.get("email") or "",
            "price_text": info_price_text(self.settings),
            "rows": rows,
            "total_quantity": sum(item["quantity"] for item in items),
            "total_volume": float(self.total_volume(items)),
            "total_cost": float(self.total_cost(items)),
        }

    def xlsx_file_name(self):
        return f"расчет_{self.number}.xlsx"

    def _needs_download_dialog(self):
        if getattr(self.page, "web", False):
            return True
        platform = getattr(self.page, "platform", None)
        is_mobile = getattr(platform, "is_mobile", None)
        return bool(is_mobile and is_mobile())

    def _attach_service(self, service):
        services = getattr(self.page, "services", None)
        if services is not None and all(
            existing is not service for existing in services
        ):
            services.append(service)

    async def save_xlsx_bytes(self, data, file_name):
        if not self._needs_download_dialog():
            path = Path(DATA_DIR) / file_name
            try:
                path.write_bytes(data)
            except OSError as exc:
                self.page.show_dialog(ft.SnackBar(
                    content=ft.Text(f"Не удалось сохранить Excel: {exc}"),
                ))
                return
            self.page.show_dialog(ft.SnackBar(
                content=ft.Text(f"Excel сохранён: {path}"),
            ))
            return

        picker = self._picker
        if picker is None:
            picker = ft.FilePicker()
            self._picker = picker
        self._attach_service(picker)
        try:
            await picker.save_file(
                dialog_title="Сохранить расчёт",
                file_name=file_name,
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["xlsx"],
                src_bytes=data,
            )
        except (OSError, ValueError) as exc:
            self.page.show_dialog(ft.SnackBar(
                content=ft.Text(f"Не удалось сохранить Excel: {exc}"),
            ))
            return
        self.page.show_dialog(ft.SnackBar(content=ft.Text("Excel сохранён")))

    async def download_xlsx(self, _):
        try:
            data = build_calculation_xlsx(self.export_calculation())
        except RuntimeError as exc:
            self.page.show_dialog(ft.SnackBar(content=ft.Text(str(exc))))
            return
        await self.save_xlsx_bytes(data, self.xlsx_file_name())

    # --------------------------------------------------------------- info

    def show_info(self, _):
        items = self.items()
        count = sum(item["quantity"] for item in items)
        diameters = [item["diameter"] for item in items]
        max_diameter = max(diameters) if diameters else 0
        min_diameter = min(diameters) if diameters else 0
        average_diameter = (
            sum(item["diameter"] * item["quantity"] for item in items) / count
            if count else 0
        )
        counterparty_name = (
            (self.settings["counterparty"] or {}).get("name") or "н/д"
        )

        def info_row(label, value):
            return ft.Row(
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text(label, size=15, color="#4F5559", expand=True),
                    ft.Text(value, size=15, weight=ft.FontWeight.BOLD,
                            color="#2B3033"),
                ],
            )

        self.page.show_dialog(ft.AlertDialog(
            modal=True,
            title=ft.Text(
                f"РАСЧЕТ # {self.number}", size=22,
                weight=ft.FontWeight.BOLD,
                text_align=ft.TextAlign.CENTER,
            ),
            content=ft.Column(
                tight=True, spacing=8,
                controls=[
                    ft.Divider(height=1, color="#2B3033"),
                    info_row("Количество бревен:", f"{count} шт."),
                    info_row("Ø max:", f"{max_diameter} см"),
                    info_row("Ø min:", f"{min_diameter} см"),
                    info_row("Ø средний:", f"{average_diameter:.1f} см"),
                    info_row("Контрагент:", counterparty_name),
                    info_row("Цена 1 м³:", info_price_text(self.settings)),
                ],
            ),
            actions=[
                ft.FilledButton(
                    "OK", on_click=lambda _: self.page.pop_dialog(),
                    width=200, height=44,
                    style=ft.ButtonStyle(bgcolor=GREEN, color="white"),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.CENTER,
        ))

    # --------------------------------------------------------------- send

    def show_send(self, _):
        try:
            data = build_calculation_xlsx(self.export_calculation())
        except RuntimeError as exc:
            self.page.show_dialog(ft.SnackBar(content=ft.Text(str(exc))))
            return
        file_name = self.xlsx_file_name()

        async def share_excel(_):
            self.page.pop_dialog()
            share = self._share
            if share is None:
                share = ft.Share()
                self._share = share
            self._attach_service(share)
            try:
                await share.share_files(
                    [ft.ShareFile.from_bytes(
                        data,
                        mime_type=(
                            "application/vnd.openxmlformats-officedocument."
                            "spreadsheetml.sheet"
                        ),
                        name=file_name,
                    )],
                    title="Отправить расчёт",
                    text=self.title,
                    subject=f"Расчёт #{self.number}",
                )
            except Exception as exc:  # noqa: BLE001 - platform error text
                self.page.show_dialog(ft.SnackBar(
                    content=ft.Text(f"Не удалось поделиться файлом: {exc}"),
                ))

        async def save_from_dialog(_):
            self.page.pop_dialog()
            await self.save_xlsx_bytes(data, file_name)

        self.page.show_dialog(ft.AlertDialog(
            modal=True,
            title=ft.Text("Отправить расчёт"),
            content=ft.Column(
                tight=True, spacing=14,
                controls=[
                    ft.Row(
                        spacing=12,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Container(
                                width=56, height=56, border_radius=12,
                                bgcolor="#E5F0E9",
                                alignment=ft.Alignment.CENTER,
                                content=ft.Icon(
                                    ft.Icons.TABLE_VIEW, color=GREEN,
                                ),
                            ),
                            ft.Column(
                                spacing=2, expand=True,
                                controls=[
                                    ft.Text(file_name, size=15,
                                            weight=ft.FontWeight.BOLD),
                                    ft.Text(self.excel_note, size=12,
                                            color=TEXT),
                                ],
                            ),
                        ],
                    ),
                    ft.Text(
                        "Отправьте таблицу в мессенджер, почту или "
                        "сохраните её на устройство.",
                        size=13, color=TEXT,
                    ),
                ],
            ),
            actions=[
                ft.TextButton("Отмена",
                              on_click=lambda _: self.page.pop_dialog()),
                ft.OutlinedButton(
                    "Скачать", icon=ft.Icons.DOWNLOAD,
                    on_click=save_from_dialog,
                ),
                ft.FilledButton(
                    "Поделиться", icon=ft.Icons.SHARE,
                    on_click=share_excel,
                    style=ft.ButtonStyle(bgcolor=GREEN, color="white"),
                ),
            ],
        ))

    # ----------------------------------------------------------- settings

    def open_settings(self, _=None):
        page = self.page
        settings = self.settings
        draft_ranges = [dict(item) for item in settings["ranges"]]
        if not draft_ranges:
            draft_ranges = [dict(item) for item in DEFAULT_PRICE_RANGES]
        draft_counterparty = dict(settings["counterparty"] or {})

        ranges_column = ft.Column(
            spacing=6,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        )

        def update_range(index, key, value):
            if 0 <= index < len(draft_ranges):
                draft_ranges[index][key] = value

        def render_ranges():
            ranges_column.controls.clear()
            for index, item in enumerate(draft_ranges):
                from_field = ft.TextField(
                    value=str(item.get("from", "")),
                    hint_text="от", width=56, dense=True, text_size=13,
                    keyboard_type=ft.KeyboardType.NUMBER,
                    on_change=lambda e, i=index: update_range(
                        i, "from", e.control.value
                    ),
                )
                to_field = ft.TextField(
                    value=str(item.get("to", "")),
                    hint_text="до", width=56, dense=True, text_size=13,
                    keyboard_type=ft.KeyboardType.NUMBER,
                    on_change=lambda e, i=index: update_range(
                        i, "to", e.control.value
                    ),
                )
                price_field = ft.TextField(
                    value=str(item.get("price", "0")),
                    hint_text="цена", expand=True, dense=True, text_size=13,
                    keyboard_type=ft.KeyboardType.NUMBER,
                    on_change=lambda e, i=index: update_range(
                        i, "price", e.control.value
                    ),
                )
                item["_from"] = from_field
                item["_to"] = to_field
                item["_price"] = price_field
                ranges_column.controls.append(ft.Row(
                    spacing=4,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        from_field,
                        ft.Text("—", color=TEXT),
                        to_field,
                        price_field,
                        ft.IconButton(
                            ft.Icons.DELETE_OUTLINE, icon_size=18,
                            tooltip="Удалить диапазон",
                            on_click=lambda e, i=index: delete_range(i),
                        ),
                    ],
                ))

        def sync_range_fields():
            for item in draft_ranges:
                if item.get("_from") is not None:
                    item["from"] = item["_from"].value
                if item.get("_to") is not None:
                    item["to"] = item["_to"].value
                if item.get("_price") is not None:
                    item["price"] = item["_price"].value

        def delete_range(index):
            sync_range_fields()
            if 0 <= index < len(draft_ranges):
                draft_ranges.pop(index)
            render_ranges()
            page.update()

        def add_range(_):
            sync_range_fields()
            draft_ranges.append({"from": "", "to": "", "price": "0"})
            render_ranges()
            page.update()

        def reset_ranges(new_ranges):
            sync_range_fields()
            draft_ranges[:] = new_ranges
            render_ranges()
            page.update()

        def use_standard_ranges(_):
            existing = {}
            for item in draft_ranges:
                try:
                    key = (int(item.get("from")), int(item.get("to")))
                except (TypeError, ValueError):
                    continue
                existing[key] = item.get("price", "0")
            reset_ranges([
                {
                    "from": entry["from"],
                    "to": entry["to"],
                    "price": existing.get(
                        (entry["from"], entry["to"]), entry["price"]
                    ),
                }
                for entry in DEFAULT_PRICE_RANGES
            ])

        def use_single_range(_):
            price = (
                draft_ranges[0].get("price", "0") if draft_ranges else "0"
            )
            reset_ranges([{"from": 3, "to": 120, "price": price}])

        def use_custom_ranges(_):
            reset_ranges([{"from": "", "to": "", "price": "0"}])

        def parse_ranges():
            sync_range_fields()
            parsed = []
            for item in draft_ranges:
                start_text = str(item.get("from", "")).strip().replace(",", ".")
                end_text = str(item.get("to", "")).strip().replace(",", ".")
                price_text = (
                    str(item.get("price", "")).strip().replace(",", ".")
                )
                if not start_text and not end_text and not price_text:
                    continue
                try:
                    start_value = Decimal(start_text)
                    end_value = Decimal(end_text)
                    price = Decimal(price_text or "0")
                    if (
                        start_value != start_value.to_integral_value()
                        or end_value != end_value.to_integral_value()
                    ):
                        raise InvalidOperation
                    start = int(start_value)
                    end = int(end_value)
                except (InvalidOperation, ValueError):
                    return None, (
                        "Укажите целые диаметры и цену в каждом диапазоне."
                    )
                if price < 0:
                    return None, "Цена не может быть отрицательной."
                if start > end:
                    start, end = end, start
                parsed.append({
                    "from": start,
                    "to": end,
                    "price": format(price.normalize(), "f"),
                })
            if not parsed:
                return None, "Добавьте хотя бы один диапазон цен."
            parsed.sort(key=lambda entry: (entry["from"], entry["to"]))
            for previous, current in pairwise(parsed):
                if current["from"] <= previous["to"]:
                    return None, "Диапазоны не должны пересекаться."
            return parsed, None

        filter_dropdown = ft.Dropdown(
            label="Показ диаметров",
            value=settings["diameter_filter"],
            dense=True,
            options=[
                ft.DropdownOption(key=key, text=text)
                for key, text in DIAMETER_FILTER_OPTIONS
            ],
        )
        species_dropdown = ft.Dropdown(
            label="Порода",
            value=settings["species"],
            dense=True,
            options=[
                ft.DropdownOption(key=item, text=item)
                for item in SPECIES_OPTIONS
            ],
        )
        calc_type_dropdown = ft.Dropdown(
            label="Тип расчёта",
            value=settings["calc_type"],
            dense=True,
            options=[
                ft.DropdownOption(key=item, text=item)
                for item in CALC_TYPE_OPTIONS
            ],
        )
        counterparty_dropdown = ft.Dropdown(
            label="Контрагент",
            value=(
                str(draft_counterparty["id"])
                if draft_counterparty.get("id") is not None
                else "none"
            ),
            dense=True,
            options=[ft.DropdownOption(key="none", text="Без контрагента")]
            + [
                ft.DropdownOption(key=str(cp["id"]), text=cp["name"])
                for cp in list_counterparties()
            ],
        )

        def selected_counterparty():
            value = counterparty_dropdown.value
            if value in (None, "", "none"):
                return {}
            selected = next(
                (cp for cp in list_counterparties()
                 if str(cp["id"]) == str(value)),
                None,
            )
            return dict(selected) if selected else {}

        def add_counterparty(_):
            cp_name = ft.TextField(label="Название")
            cp_phone = ft.TextField(label="Телефон")
            cp_email = ft.TextField(label="Email")
            cp_info = ft.TextField(label="Дополнительная информация")

            def save_cp(_):
                try:
                    cp_id = save_counterparty(
                        cp_name.value, cp_phone.value,
                        cp_email.value, cp_info.value,
                    )
                except ValueError as exc:
                    cp_name.error_text = str(exc)
                    page.update()
                    return
                page.pop_dialog()
                counterparty_dropdown.options = (
                    [ft.DropdownOption(key="none", text="Без контрагента")]
                    + [
                        ft.DropdownOption(key=str(cp["id"]), text=cp["name"])
                        for cp in list_counterparties()
                    ]
                )
                counterparty_dropdown.value = str(cp_id)
                draft_counterparty.clear()
                selected = next(
                    (cp for cp in list_counterparties() if cp["id"] == cp_id),
                    None,
                )
                if selected:
                    draft_counterparty.update(selected)
                page.update()

            page.show_dialog(ft.AlertDialog(
                modal=True,
                title=ft.Text("Новый контрагент"),
                content=ft.Column(
                    tight=True, spacing=10,
                    controls=[cp_name, cp_phone, cp_email, cp_info],
                ),
                actions=[
                    ft.TextButton("Отмена",
                                  on_click=lambda _: page.pop_dialog()),
                    ft.FilledButton(
                        "Сохранить", on_click=save_cp,
                        style=ft.ButtonStyle(bgcolor=GREEN, color="white"),
                    ),
                ],
            ))

        def apply_settings(_):
            ranges, error = parse_ranges()
            if error:
                # An inline error stays visible above the dialog; a SnackBar
                # would be drawn underneath the modal and get hidden.
                range_error.value = error
                range_error.visible = True
                page.update()
                return
            range_error.value = ""
            range_error.visible = False
            previous_filter = settings["diameter_filter"]
            settings["ranges"] = ranges
            settings["diameter_filter"] = filter_dropdown.value or "all"
            settings["species"] = species_dropdown.value or "н/д"
            settings["calc_type"] = calc_type_dropdown.value or "продажа"
            settings["counterparty"] = selected_counterparty()
            page.pop_dialog()
            self.refresh()
            if self.on_settings_changed:
                self.on_settings_changed()
            page.update()
            if (
                settings["diameter_filter"] != previous_filter
                and self.on_filter_changed
            ):
                self.on_filter_changed(settings["diameter_filter"])

        def section_title(text):
            return ft.Text(text, size=14, color=GREEN,
                           weight=ft.FontWeight.BOLD)

        render_ranges()
        range_error = ft.Text(
            "", size=12, color="#B3261E", visible=False, no_wrap=False,
        )
        dialog_width = min(
            max((getattr(page, "width", None) or 420) - 16, 300), 600,
        )
        page.show_dialog(ft.AlertDialog(
            modal=True,
            title=ft.Text("Настройки расчёта", weight=ft.FontWeight.BOLD),
            content=ft.Container(
                width=dialog_width,
                height=min(
                    (getattr(page, "height", None) or 760) * 0.74, 620,
                ),
                content=ft.Column(
                    tight=True, spacing=10,
                    scroll=ft.ScrollMode.AUTO,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    controls=[
                        section_title("Цена по диапазонам, RUB/м³"),
                        ft.Row(
                            wrap=True, spacing=6, run_spacing=6,
                            controls=[
                                ft.OutlinedButton(
                                    "Стандартные",
                                    on_click=use_standard_ranges,
                                ),
                                ft.OutlinedButton(
                                    "Один диапазон",
                                    on_click=use_single_range,
                                ),
                                ft.OutlinedButton(
                                    "Свои диапазоны",
                                    on_click=use_custom_ranges,
                                ),
                            ],
                        ),
                        ranges_column,
                        range_error,
                        ft.Row(controls=[
                            ft.TextButton(
                                "Добавить диапазон",
                                icon=ft.Icons.ADD,
                                on_click=add_range,
                            ),
                        ]),
                        ft.Divider(height=1, color="#E4E8E4"),
                        filter_dropdown,
                        species_dropdown,
                        calc_type_dropdown,
                        counterparty_dropdown,
                        ft.Row(controls=[
                            ft.OutlinedButton(
                                "Добавить контрагента",
                                icon=ft.Icons.PERSON_ADD_ALT_1_OUTLINED,
                                on_click=add_counterparty,
                            ),
                        ]),
                    ],
                ),
            ),
            inset_padding=ft.Padding.symmetric(horizontal=8, vertical=8),
            actions=[
                ft.TextButton("Отмена",
                              on_click=lambda _: page.pop_dialog()),
                ft.FilledButton(
                    "Применить", on_click=apply_settings,
                    style=ft.ButtonStyle(bgcolor=GREEN, color="white"),
                ),
            ],
        ))
