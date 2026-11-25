from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import flet as ft

from app.cylindering import show_cylindering
from app.storage import init_db, list_calculations

GREEN = "#176B4A"
ORANGE = "#E89A4E"
BG = "#F7F8F7"
PANEL = "#E8E9EA"
TEXT = "#62666A"
DIAMETERS = list(range(4, 101))
UNIT_NAMES = {"MM": "мм", "CM": "см", "M": "м"}


def main(page: ft.Page):
    init_db()
    page.title = "Расчёт кубатуры"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = BG
    page.padding = 0
    page.window_min_width = 360
    page.window_min_height = 640

    current_items = []
    lumber_items = []
    selected_length = {"value": 6.0}
    active_tab = {"value": "table"}

    def menu_card(title, subtitle, action):
        return ft.Card(
            elevation=0,
            bgcolor="#F0F1EF",
            content=ft.ListTile(
                title=ft.Text(title, size=19, weight=ft.FontWeight.W_600),
                subtitle=ft.Text(subtitle, size=12),
                trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT),
                on_click=action,
                content_padding=ft.Padding.symmetric(horizontal=16, vertical=8),
            ),
        )

    def show_home():
        page.controls.clear()
        page.appbar = ft.AppBar(
            title=ft.Text("Расчёт кубатуры", weight=ft.FontWeight.W_600),
            bgcolor=GREEN,
            color="white",
            center_title=True,
        )
        page.add(
            ft.Container(
                padding=18,
                content=ft.Column(
                    spacing=12,
                    controls=[
                        ft.Container(
                            padding=18,
                            border_radius=20,
                            bgcolor="#E5F0E9",
                            content=ft.Text(
                                "Автономный режим · данные хранятся на устройстве",
                                color="#3E5549",
                                size=15,
                            ),
                        ),
                        menu_card(
                            "ГОСТ 2708-75 · Таблица 1",
                            "Расчёт круглых лесоматериалов",
                            lambda _: show_gost_calculator(),
                        ),
                        menu_card(
                            "Пиломатериалы",
                            "Расчёт досок и бруса",
                            lambda _: show_lumber_calculator(),
                        ),

menu_card(
    "Оцилиндровка",
    "Расчёт объёма оцилиндрованных брёвен",
    lambda _: show_cylindering(page, show_home),
),
                        ft.OutlinedButton(
                            "История расчётов",
                            icon=ft.Icons.HISTORY,
                            on_click=lambda _: show_history(),
                        ),
                    ],
                ),
            )
        )
        page.update()

    def show_placeholder(title):
        page.controls.clear()
        page.appbar = ft.AppBar(
            leading=ft.IconButton(ft.Icons.ARROW_BACK, on_click=lambda _: show_home()),
            title=ft.Text(title),
            bgcolor=GREEN,
            color="white",
        )
        page.add(
            ft.Container(
                padding=24,
                content=ft.Text(
                    "Этот раздел пока не реализован. "
                    "Табличные данные не подставляются до проверки источника.",
                    size=16,
                ),
            )
        )
        page.update()

    def show_gost_calculator():
        page.controls.clear()
        active_tab["value"] = "table"
        page.appbar = ft.AppBar(
            leading=ft.IconButton(ft.Icons.ARROW_BACK, on_click=lambda _: show_home()),
            title=ft.Text("Расчёт · ГОСТ 2708-75", size=18),
            bgcolor=GREEN,
            color="white",
            center_title=True,
        )

        total_volume = ft.Text("—", size=25, color=ORANGE, weight=ft.FontWeight.BOLD)
        total_count = ft.Text("0 шт.", size=17, color=TEXT)
        items_column = ft.Column(spacing=7, scroll=ft.ScrollMode.AUTO, expand=True)
        table_view = ft.Row(spacing=8, expand=True,
                            vertical_alignment=ft.CrossAxisAlignment.STRETCH)
        summary_view = ft.Column(spacing=12, expand=True)
        content_host = ft.Container(expand=True, content=table_view)

        def refresh_summary():
            summary_view.controls.clear()
            summary_view.controls.extend([
                ft.Text("Итоги расчёта", size=22, weight=ft.FontWeight.BOLD),
                ft.Row(controls=[
                    ft.Text("Количество брёвен", size=16),
                    ft.Container(expand=True),
                    ft.Text(total_count.value, size=17, weight=ft.FontWeight.BOLD),
                ]),
                ft.Row(controls=[
                    ft.Text("Общая кубатура", size=16),
                    ft.Container(expand=True),
                    ft.Text("Не рассчитана", size=17, color=ORANGE,
                            weight=ft.FontWeight.BOLD),
                ]),
                ft.Text(
                    "Для расчёта объёма необходимы проверенные значения "
                    "таблицы ГОСТ 2708-75.",
                    size=13, color=TEXT,
                ),
            ])

        def refresh_items():
            items_column.controls.clear()
            if not current_items:
                items_column.controls.append(
                    ft.Container(
                        padding=16,
                        content=ft.Text("Нажмите на диаметр, чтобы добавить бревно.",
                                        color=TEXT),
                    )
                )
            for index, item in enumerate(current_items):
                items_column.controls.append(
                    ft.Container(
                        padding=ft.Padding.symmetric(horizontal=8, vertical=9),
                        border_radius=10,
                        bgcolor=PANEL,
                        content=ft.Row(
                            spacing=7,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            controls=[
                                ft.Container(
                                    width=58, height=54, border_radius=10,
                                    bgcolor="#F5F6F6", alignment=ft.Alignment.CENTER,
                                    content=ft.Text(
                                        f"Ø{item['diameter']}", size=18,
                                        weight=ft.FontWeight.W_600, color=TEXT,
                                        no_wrap=True,
                                    ),
                                ),
                                ft.Row(
                                    spacing=5, expand=True,
                                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                    controls=[
                                        ft.Text(f"{item['length']:.1f} м", size=13,
                                                color=TEXT, no_wrap=True),
                                        ft.Text("·", size=13, color=TEXT),
                                        ft.Text(f"{item['quantity']} шт.", size=13,
                                                color=TEXT, no_wrap=True),
                                    ],
                                ),
                                ft.Column(
                                    spacing=0,
                                    horizontal_alignment=ft.CrossAxisAlignment.END,
                                    controls=[
                                        ft.Text("—", size=20, color=ORANGE,
                                                weight=ft.FontWeight.BOLD),
                                        ft.IconButton(
                                            ft.Icons.DELETE_OUTLINE,
                                            icon_color=TEXT, icon_size=20,
                                            tooltip="Удалить позицию",
                                            on_click=lambda e, i=index: remove_item(i),
                                        ),
                                    ],
                                ),
                            ],
                        ),
                    )
                )
            total_count.value = f"{sum(x['quantity'] for x in current_items)} шт."
            total_volume.value = "—"
            if active_tab["value"] == "summary":
                refresh_summary()
            page.update()

        def remove_item(index):
            if 0 <= index < len(current_items):
                current_items.pop(index)
                refresh_items()

        def add_diameter(diameter):
            current_items.append({
                "diameter": diameter,
                "length": selected_length["value"],
                "quantity": 1,
                "volume": None,
                "display_volume": "—",
                "status": "Ожидает проверенных данных таблицы ГОСТ",
            })
            refresh_items()

        def choose_tab(tab_name):
            active_tab["value"] = tab_name
            is_table = tab_name == "table"
            content_host.content = table_view if is_table else summary_view
            table_tab.style = ft.ButtonStyle(
                color="white" if is_table else "#B8D4C8",
                bgcolor=GREEN, shape=ft.RoundedRectangleBorder(radius=0),
            )
            summary_tab.style = ft.ButtonStyle(
                color="white" if not is_table else "#B8D4C8",
                bgcolor=GREEN, shape=ft.RoundedRectangleBorder(radius=0),
            )
            if not is_table:
                refresh_summary()
            page.update()

        def open_length_picker(_):
            length_input = ft.TextField(
                label="Длина, м", value=f"{selected_length['value']:.1f}",
                keyboard_type=ft.KeyboardType.NUMBER, autofocus=True,
            )

            def set_length(_):
                try:
                    value = float(length_input.value.replace(",", "."))
                    if value <= 0:
                        raise ValueError
                except (TypeError, ValueError, AttributeError):
                    page.show_dialog(ft.SnackBar(
                        content=ft.Text("Введите корректную длину больше нуля.")
                    ))
                    return
                selected_length["value"] = value
                length_button.content = ft.Row(tight=True, controls=[
                    ft.Icon(ft.Icons.STRAIGHTEN, color="white"),
                    ft.Text(f"ДЛИНА: {value:g}", color="white",
                            weight=ft.FontWeight.BOLD),
                ])
                page.pop_dialog()
                page.update()

            def set_preset(value):
                length_input.value = f"{value:g}"
                set_length(None)

            page.show_dialog(ft.AlertDialog(
                modal=True,
                title=ft.Text("Выбор длины"),
                content=ft.Column(tight=True, controls=[
                    length_input,
                    ft.Row(wrap=True, controls=[
                        ft.TextButton(f"{v:g} м",
                                      on_click=lambda e, n=v: set_preset(n))
                        for v in (4.0, 4.5, 5.0, 6.0, 6.5, 7.0, 8.0)
                    ]),
                ]),
                actions=[
                    ft.TextButton("Отмена", on_click=lambda _: page.pop_dialog()),
                    ft.FilledButton("Применить", on_click=set_length),
                ],
            ))

        diameter_grid = ft.GridView(
            expand=True, runs_count=2, spacing=5, run_spacing=5,
            child_aspect_ratio=1.0,
            controls=[
                ft.FilledButton(
                    content=ft.Text(str(d), size=22, no_wrap=True,
                                    text_align=ft.TextAlign.CENTER),
                    height=58,
                    style=ft.ButtonStyle(
                        bgcolor="#E5E6E7", color=TEXT,
                        padding=ft.Padding.symmetric(horizontal=2, vertical=4),
                        shape=ft.RoundedRectangleBorder(radius=5), elevation=0,
                    ),
                    on_click=lambda e, n=d: add_diameter(n),
                )
                for d in DIAMETERS
            ],
        )
        table_view.controls = [
            ft.Container(
                expand=3, padding=4, border=ft.Border.all(1, "#D8DADC"),
                border_radius=7, bgcolor="#FCFCFC", content=items_column,
            ),
            ft.Container(
                expand=2, padding=ft.Padding.only(left=2, right=2),
                content=diameter_grid,
            ),
        ]

        table_tab = ft.TextButton(
            "Таблица", expand=True, on_click=lambda _: choose_tab("table"),
            style=ft.ButtonStyle(color="white", bgcolor=GREEN),
        )
        summary_tab = ft.TextButton(
            "Итоги", expand=True, on_click=lambda _: choose_tab("summary"),
            style=ft.ButtonStyle(color="#B8D4C8", bgcolor=GREEN),
        )
        length_button = ft.FilledButton(
            content=ft.Row(tight=True, controls=[
                ft.Icon(ft.Icons.STRAIGHTEN, color="white"),
                ft.Text("ДЛИНА: 6", color="white", weight=ft.FontWeight.BOLD),
            ]),
            style=ft.ButtonStyle(bgcolor="#8C918F", color="white"),
            on_click=open_length_picker,
        )

        page.add(ft.Column(
            spacing=0, expand=True,
            controls=[
                ft.Row(controls=[table_tab, summary_tab], spacing=0),
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=12, vertical=7),
                    content=ft.Row(controls=[
                        ft.Icon(ft.Icons.TUNE, color="#85898C", size=25),
                        total_volume, ft.Container(expand=True), total_count,
                    ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ),
                ft.Container(content=content_host, expand=True,
                             padding=ft.Padding.symmetric(horizontal=8)),
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=8, vertical=7),
                    content=ft.Row(controls=[
                        ft.FilledButton(
                            content=ft.Row(tight=True, controls=[
                                ft.Icon(ft.Icons.SAVE, color="white"),
                                ft.Text("Сохранить", color="white",
                                        weight=ft.FontWeight.BOLD),
                            ]),
                            expand=True, disabled=True,
                            style=ft.ButtonStyle(bgcolor="#AEB5B1", color="#E7E9E8"),
                        ),
                        length_button,
                    ], spacing=7),
                ),
            ],
        ))
        refresh_items()
        page.update()

    def lumber_volume(item):
        return (
            Decimal(str(item["thickness_cm"])) / Decimal(100)
            * Decimal(str(item["width_cm"])) / Decimal(100)
            * Decimal(str(item["length_m"]))
            * int(item["quantity"])
        )

    def show_lumber_calculator():
        page.controls.clear()
        page.appbar = ft.AppBar(
            leading=ft.IconButton(ft.Icons.ARROW_BACK, on_click=lambda _: show_home()),
            title=ft.Text("Расчёт #1\n(ПИЛОМАТЕРИАЛЫ)", size=18),
            bgcolor=GREEN, color="white",
            actions=[
                ft.PopupMenuButton(
                    icon=ft.Icons.MORE_VERT,
                    tooltip="Меню",
                    items=[
                        ft.PopupMenuItem(
                            content=ft.Text("Очистить записи"),
                            on_click=lambda _: confirm_clear_records(),
                        ),
                    ],
                )
            ],
        )

        summary_volume = ft.Text("0.0000 м³", size=28, color=ORANGE,
                                  weight=ft.FontWeight.BOLD)
        summary_details = ft.Text("0 шт. · 0.00 RUB.", size=16, color=TEXT)
        records = ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO, expand=True)
        price_currency = "RUB."
        rounding_digits = {"value": 4}  # По умолчанию 0.0000

        def fmt(value, places=None):
            if places is None:
                places = rounding_digits["value"]
            return f"{value:.{places}f}"

        def rounded_volume(item):
            quantum = Decimal(1).scaleb(-rounding_digits["value"])
            return lumber_volume(item).quantize(
                quantum, rounding=ROUND_HALF_UP
            )

        def update_summary():
            # Каждая позиция сначала округляется, затем значения складываются.
            total_volume = sum(
                (rounded_volume(x) for x in lumber_items), Decimal(0)
            )
            total_count = sum(int(x["quantity"]) for x in lumber_items)
            total_price = sum((
                rounded_volume(x) * Decimal(str(x.get("price_per_m3", 0)))
                for x in lumber_items
            ), Decimal(0))
            summary_volume.value = f"{fmt(total_volume)} м³"
            summary_details.value = (
                f"{total_count} шт. · {fmt(total_price, 2)} {price_currency}"
            )

        def confirm_clear_records():
            def clear(_):
                lumber_items.clear()
                page.pop_dialog()
                refresh_records()

            page.show_dialog(ft.AlertDialog(
                modal=True,
                title=ft.Text("Очистить записи?"),
                content=ft.Text("Все добавленные позиции будут удалены."),
                actions=[
                    ft.TextButton("Отмена", on_click=lambda _: page.pop_dialog()),
                    ft.TextButton("Очистить", on_click=clear),
                ],
            ))

        def delete_lumber(index):
            if 0 <= index < len(lumber_items):
                lumber_items.pop(index)
                refresh_records()

        def open_record_menu(index):
            def edit(_):
                page.pop_dialog()
                open_lumber_editor(index=index)

            def delete(_):
                page.pop_dialog()
                delete_lumber(index)

            page.show_dialog(ft.AlertDialog(
                modal=True,
                title=ft.Text("Позиция"),
                actions=[
                    ft.TextButton("Изменить", on_click=edit),
                    ft.TextButton("Удалить", on_click=delete),
                ],
            ))

        def display_dimension(value, unit, base_unit):
            value = Decimal(str(value))
            if base_unit == "cm":
                scale = {"MM": Decimal(10), "CM": Decimal(1),
                         "M": Decimal("0.01")}
            else:
                scale = {"MM": Decimal(1000), "CM": Decimal(100),
                         "M": Decimal(1)}
            return value * scale[unit]

        def refresh_records():
            records.controls.clear()
            if not lumber_items:
                records.controls.append(
                    ft.Container(
                        expand=True, alignment=ft.Alignment.CENTER,
                        padding=20,
                        content=ft.Text(
                            "Добавьте первую позицию",
                            size=16, color=TEXT,
                            text_align=ft.TextAlign.CENTER,
                        ),
                    )
                )

            for index, item in enumerate(lumber_items):
                volume = rounded_volume(item)
                price = volume * Decimal(str(item.get("price_per_m3", 0)))
                unit_volume = (
                    Decimal(str(item["thickness_cm"])) / Decimal(100)
                    * Decimal(str(item["width_cm"])) / Decimal(100)
                    * Decimal(str(item["length_m"]))
                )
                per_cubic = (
                    Decimal(1) / unit_volume if unit_volume > 0 else None
                )
                legacy_unit = item.get("unit", "CM")
                t_unit = item.get("thickness_unit", legacy_unit)
                w_unit = item.get("width_unit", legacy_unit)
                l_unit = item.get("length_unit", legacy_unit)

                thickness = display_dimension(item["thickness_cm"], t_unit, "cm")
                width = display_dimension(item["width_cm"], w_unit, "cm")
                length = display_dimension(item["length_m"], l_unit, "m")
                dims = (
                    f"{thickness.normalize():f} {UNIT_NAMES[t_unit]} × "
                    f"{width.normalize():f} {UNIT_NAMES[w_unit]} × "
                    f"{length.normalize():f} {UNIT_NAMES[l_unit]}"
                )

                records.controls.append(
                    ft.Container(
                        padding=ft.Padding.symmetric(horizontal=10, vertical=8),
                        border=ft.Border.all(1, "#E0E2E1"),
                        border_radius=14,
                        bgcolor="#FFFFFF",
                        content=ft.Column(
                            spacing=4,
                            controls=[
                                ft.Row(
                                    spacing=2,
                                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                    controls=[
                                        ft.Text(
                                            dims, size=15, color=GREEN,
                                            weight=ft.FontWeight.BOLD,
                                            expand=True, no_wrap=True,
                                            max_lines=1,
                                        ),
                                    ],
                                ),
                                ft.Row(
                                    spacing=2,
                                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                    controls=[
                                        ft.Container(
                                            padding=ft.Padding.symmetric(
                                                horizontal=7, vertical=5
                                            ),
                                            border_radius=10, bgcolor="#F0F3F1",
                                            on_click=lambda e, i=index: (
                                                open_lumber_editor(index=i, focus="quantity")
                                            ),
                                            content=ft.Row(tight=True, spacing=2,
                                                controls=[
                                                    ft.Text(
                                                        f"{item['quantity']} шт.",
                                                        color=GREEN,
                                                        weight=ft.FontWeight.BOLD,
                                                        size=13, no_wrap=True,
                                                    ),
                                                    ft.Icon(ft.Icons.EDIT, size=14,
                                                            color=GREEN),
                                                ]),
                                        ),
                                        ft.IconButton(
                                            ft.Icons.CONTENT_COPY,
                                            icon_color=GREEN, icon_size=19,
                                            tooltip="Дублировать",
                                            on_click=lambda e, i=index: (
                                                open_lumber_editor(duplicate=i)
                                            ),
                                        ),
                                        ft.IconButton(
                                            ft.Icons.MORE_VERT,
                                            icon_color=TEXT, icon_size=19,
                                            tooltip="Опции",
                                            on_click=lambda e, i=index: open_record_menu(i),
                                        ),
                                        ft.Container(expand=True),
                                        ft.Text(
                                            f"{fmt(volume)} м³",
                                            size=19, color=ORANGE,
                                            weight=ft.FontWeight.BOLD,
                                        ),
                                    ],
                                ),
                                ft.Row(
                                    controls=[
                                        ft.Text(
                                            (
                                                f"В 1 м³: ≈ "
                                                f"{int(per_cubic.to_integral_value(rounding='ROUND_HALF_UP'))} шт."
                                            ) if per_cubic is not None else "В 1 м³: —",
                                            size=12, color=TEXT,
                                        ),
                                        ft.Container(expand=True),
                                        ft.Column(
                                            spacing=0,
                                            horizontal_alignment=ft.CrossAxisAlignment.END,
                                            controls=[
                                                ft.Text(
                                                    f"{fmt(price, 2)} {price_currency}"
                                                    if item.get("price_per_m3") else "",
                                                    size=12, color=GREEN,
                                                    weight=ft.FontWeight.BOLD,
                                                ),
                                            ],
                                        ),
                                    ],
                                    vertical_alignment=ft.CrossAxisAlignment.END,
                                ),
                            ],
                        ),
                    )
                )

            update_summary()
            page.update()

        def open_lumber_editor(index=None, duplicate=None, focus="thickness"):
            if duplicate is not None:
                data = dict(lumber_items[duplicate])
                title = f"Новая позиция на основе №{duplicate + 1}"
            elif index is not None:
                data = dict(lumber_items[index])
                title = f"Позиция {index + 1}"
            else:
                data = {
                    "thickness_cm": 0,
                    "width_cm": 0,
                    "length_m": 0,
                    "quantity": 1,
                    "price_per_m3": 0,
                    "thickness_unit": "CM",
                    "width_unit": "CM",
                    "length_unit": "M",
                }
                title = "Новый пиломатериал"

            field_order = [
                "thickness_cm", "width_cm", "length_m",
                "quantity", "price_per_m3",
            ]
            labels = {
                "thickness_cm": ("Толщина:", "см"),
                "width_cm": ("Ширина:", "см"),
                "length_m": ("Длина:", "м"),
                "quantity": ("Кол-во:", "шт."),
                "price_per_m3": ("Цена:", f"{price_currency}/м³"),
            }
            focus = {
                "thickness": "thickness_cm",
                "width": "width_cm",
                "length": "length_m",
            }.get(focus, focus)
            if focus not in field_order:
                focus = "thickness_cm"

            legacy_unit = data.get("unit", "CM")
            unit_modes = {
                "thickness_cm": {"value": data.get("thickness_unit", legacy_unit)},
                "width_cm": {"value": data.get("width_unit", legacy_unit)},
                "length_m": {"value": data.get("length_unit", legacy_unit)},
            }
            fields, unit_texts, field_rows, unit_buttons = {}, {}, {}, {}
            rows = []
            active_field = {"value": focus}

            volume_label = ft.Text("0.0000", size=22, color=ORANGE,
                                   weight=ft.FontWeight.BOLD)
            price_label = ft.Text("0.00", size=16, color="#AAB1B1",
                                  weight=ft.FontWeight.BOLD)
            per_cubic_label = ft.Text("В 1 м³: —", size=12, color=TEXT)

            def shown_value(key):
                value = Decimal(str(data[key]))
                if key in ("thickness_cm", "width_cm"):
                    unit = unit_modes[key]["value"]
                    if unit == "MM":
                        value *= Decimal(10)
                    elif unit == "M":
                        value /= Decimal(100)
                elif key == "length_m":
                    unit = unit_modes[key]["value"]
                    if unit == "MM":
                        value *= Decimal(1000)
                    elif unit == "CM":
                        value *= Decimal(100)
                return format(value.normalize(), "f")

            def refresh_calculations():
                unit_volume = (
                    Decimal(str(data["thickness_cm"])) / Decimal(100)
                    * Decimal(str(data["width_cm"])) / Decimal(100)
                    * Decimal(str(data["length_m"]))
                )
                volume_label.value = fmt(lumber_volume(data))
                price_label.value = fmt(
                    lumber_volume(data) * Decimal(str(data.get("price_per_m3", 0))),
                    2,
                )
                if unit_volume > 0:
                    count = Decimal(1) / unit_volume
                    per_cubic_label.value = (
                        f"В 1 м³: ≈ {int(count.to_integral_value(rounding='ROUND_HALF_UP'))} шт."
                    )
                else:
                    per_cubic_label.value = "В 1 м³: —"

            def parse_field_value(key, text):
                """Привести введённое значение к внутренним см/м/шт."""
                if text is None:
                    return None
                text = str(text).strip().replace(",", ".")
                if not text:
                    return Decimal(0)
                try:
                    number = Decimal(text)
                except InvalidOperation:
                    return None
                if not number.is_finite() or number < 0:
                    return None
                if key == "quantity":
                    return int(number)
                if key in unit_modes:
                    unit = unit_modes[key]["value"]
                    if key in ("thickness_cm", "width_cm"):
                        if unit == "MM":
                            number /= Decimal(10)
                        elif unit == "M":
                            number *= Decimal(100)
                    elif key == "length_m":
                        if unit == "MM":
                            number /= Decimal(1000)
                        elif key == "CM":
                            number /= Decimal(100)
                return number

            def apply_field_value(key, text, refresh=True):
                number = parse_field_value(key, text)
                if number is None:
                    return False
                data[key] = number
                if refresh:
                    refresh_calculations()
                return True

            def update_editor_values():
                for key, field in fields.items():
                    field.value = shown_value(key)
                refresh_calculations()

            def select_field(key):
                if key not in field_order:
                    return
                active_field["value"] = key
                for name, container in field_rows.items():
                    container.bgcolor = "#DDF2E3" if name == key else "#FFFFFF"
                    container.border = ft.Border.all(
                        2 if name == key else 1,
                        GREEN if name == key else "#E1E3E2",
                    )
                refresh_unit_buttons()
                page.update()

            def refresh_unit_buttons():
                key = active_field["value"]
                selected_unit = (
                    unit_modes[key]["value"] if key in unit_modes else None
                )
                for unit, button in unit_buttons.items():
                    button.style = ft.ButtonStyle(
                        bgcolor=GREEN if unit == selected_unit else "#F0F2F1",
                        color="white" if unit == selected_unit else "#171A18",
                        padding=ft.Padding.all(2),
                    )

            for key in field_order:
                label, default_unit = labels[key]
                field = ft.TextField(
                    value=shown_value(key),
                    keyboard_type=ft.KeyboardType.NUMBER,
                    border=ft.InputBorder.NONE, text_size=16,
                    text_align=ft.TextAlign.START, expand=True,
                    bgcolor="#FFFFFF",
                    on_focus=lambda e, k=key: select_field(k),
                    on_change=lambda e, k=key: apply_field_value(
                        k, e.control.value
                    ),
                )
                fields[key] = field
                unit_label = (
                    UNIT_NAMES[unit_modes[key]["value"]]
                    if key in unit_modes else default_unit
                )
                unit_control = ft.Text(
                    unit_label, size=14, color="#171A18", width=38
                )
                unit_texts[key] = unit_control
                row = ft.Container(
                    height=54,
                    padding=ft.Padding.symmetric(horizontal=4, vertical=0),
                    border=ft.Border.all(1, "#E1E3E2"),
                    border_radius=9, bgcolor="#FFFFFF",
                    on_click=lambda e, k=key: select_field(k),
                    content=ft.Row(spacing=4, controls=[
                        ft.Text(label, size=13, color="#171A18", width=91),
                        unit_control, field,
                    ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                )
                field_rows[key] = row
                rows.append(row)

            def change_unit(unit):
                key = active_field["value"]
                if key not in unit_modes:
                    return
                unit_modes[key]["value"] = unit
                # Число в поле не пересчитывается: оно остаётся таким, каким
                # его ввёл пользователь, меняется только единица измерения.
                apply_field_value(key, fields[key].value)
                unit_texts[key].value = UNIT_NAMES[unit]
                refresh_unit_buttons()
                page.update()

            def make_unit_button(unit):
                button = ft.FilledButton(
                    unit, expand=True, height=36,
                    style=ft.ButtonStyle(
                        bgcolor="#F0F2F1", color="#171A18",
                        padding=ft.Padding.all(2),
                    ),
                    on_click=lambda e, u=unit: change_unit(u),
                )
                unit_buttons[unit] = button
                return button

            unit_row = ft.Row(
                spacing=4,
                controls=[make_unit_button(unit) for unit in ("MM", "CM", "M")],
            )

            def confirm_delete():
                close_editor = {"value": False}

                def on_dismiss(_):
                    # В вебе два pop_dialog() подряд в одном обработчике
                    # могут не сработать (второй диалог остаётся открытым),
                    # поэтому редактор закрываем только после того, как окно
                    # подтверждения действительно закрылось.
                    if close_editor["value"]:
                        page.pop_dialog()

                def delete(_):
                    close_editor["value"] = True
                    page.pop_dialog()
                    if index is not None:
                        delete_lumber(index)

                def cancel(_):
                    close_editor["value"] = False
                    page.pop_dialog()

                page.show_dialog(ft.AlertDialog(
                    modal=True,
                    title=ft.Text("Удалить запись?"),
                    content=ft.Text("Текущая позиция будет закрыта без сохранения."),
                    actions=[
                        ft.TextButton("Отмена", on_click=cancel),
                        ft.TextButton("Удалить", on_click=delete),
                    ],
                    on_dismiss=on_dismiss,
                ))

            def commit(_):
                # Перед сохранением подхватываем актуальный текст полей:
                # значения могли быть изменены без события on_change.
                for key in field_order:
                    if not apply_field_value(key, fields[key].value, refresh=False):
                        page.show_dialog(ft.SnackBar(
                            content=ft.Text("Проверьте размеры, количество и цену.")
                        ))
                        return
                try:
                    for key in ("thickness_cm", "width_cm", "length_m"):
                        if Decimal(str(data[key])) <= 0:
                            raise ValueError
                    if int(data["quantity"]) < 1:
                        raise ValueError
                    if Decimal(str(data.get("price_per_m3", 0))) < 0:
                        raise ValueError
                    data["thickness_unit"] = unit_modes["thickness_cm"]["value"]
                    data["width_unit"] = unit_modes["width_cm"]["value"]
                    data["length_unit"] = unit_modes["length_m"]["value"]
                    data.pop("unit", None)
                except (ValueError, InvalidOperation, KeyError):
                    page.show_dialog(ft.SnackBar(
                        content=ft.Text("Проверьте размеры, количество и цену.")
                    ))
                    return
                if index is None:
                    lumber_items.append(dict(data))
                else:
                    lumber_items[index] = dict(data)
                page.pop_dialog()
                refresh_records()

            editor_content = ft.Column(
                tight=True, scroll=ft.ScrollMode.AUTO, spacing=3,
                controls=[
                    ft.Row(spacing=2, controls=[
                        ft.Text(title, size=14, color=TEXT, expand=True),
                        ft.IconButton(
                            ft.Icons.DELETE_OUTLINE, icon_color=TEXT,
                            icon_size=19, padding=2,
                            tooltip="Удалить запись",
                            on_click=lambda _: confirm_delete(),
                        ),
                    ]),
                    ft.Row(controls=[volume_label, price_label], spacing=10),
                    *rows,
                    per_cubic_label,
                    unit_row,
                    ft.FilledButton(
                        "OK", expand=True, height=44, width=120,
                        style=ft.ButtonStyle(bgcolor="#E77C3B", color="white"),
                        on_click=commit,
                    ),
                ],
            )
            page.show_dialog(ft.AlertDialog(
                modal=True,
                content=ft.Container(
                    width=520,
                    height=min((page.height or 800) * 0.76, 620),
                    content=editor_content,
                ),
                shape=ft.RoundedRectangleBorder(radius=18),
                inset_padding=ft.Padding.symmetric(horizontal=8, vertical=8),
            ))
            select_field(focus)
            update_editor_values()

        def add_lumber(_):
            open_lumber_editor()

        page.add(ft.Column(
            spacing=0, expand=True,
            controls=[
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=18, vertical=10),
                    bgcolor="#FFFFFF",
                    content=ft.Column(spacing=0, controls=[
                        summary_volume, summary_details,
                    ]),
                ),
                ft.Container(
                    expand=True,
                    padding=ft.Padding.symmetric(horizontal=10, vertical=8),
                    bgcolor="#FFFFFF", border_radius=12,
                    content=records,
                ),
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=12, vertical=10),
                    bgcolor=BG,
                    content=ft.FilledButton(
                        content=ft.Row(
                            alignment=ft.MainAxisAlignment.CENTER,
                            controls=[
                                ft.Icon(ft.Icons.ADD, color="white"),
                                ft.Text(
                                    "Добавить пиломатериал", color="white",
                                    weight=ft.FontWeight.BOLD, size=17,
                                ),
                            ],
                        ),
                        expand=True, height=62,
                        style=ft.ButtonStyle(
                            bgcolor="#E77C3B", color="white",
                            shape=ft.RoundedRectangleBorder(radius=18),
                        ),
                        on_click=add_lumber,
                    ),
                ),
            ],
        ))
        refresh_records()
        page.update()

    def show_history():
        page.controls.clear()
        page.appbar = ft.AppBar(
            leading=ft.IconButton(ft.Icons.ARROW_BACK, on_click=lambda _: show_home()),
            title=ft.Text("История расчётов"),
            bgcolor=GREEN, color="white",
        )
        saved = list_calculations()
        controls = []
        if not saved:
            controls.append(ft.Text("Сохранённых расчётов пока нет."))
        for item in saved:
            controls.append(ft.ListTile(
                title=ft.Text(item["name"]),
                subtitle=ft.Text(item["created_at"]),
                trailing=ft.Text(f"{item['items_count']} поз."),
            ))
        page.add(ft.Container(
            padding=18, content=ft.Column(controls, spacing=8)
        ))
        page.update()

    show_home()


if __name__ == "__main__":
    ft.app(target=main)