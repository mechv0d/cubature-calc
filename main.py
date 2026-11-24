from decimal import Decimal, InvalidOperation

import flet as ft

from app.storage import init_db, list_calculations, save_calculation

GREEN = "#176B4A"
ORANGE = "#E89A4E"
BG = "#F7F8F7"
PANEL = "#E8E9EA"
TEXT = "#62666A"
DIAMETERS = list(range(4, 101))


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
                        menu_card("ОСТ 13-232-87", "В разработке", lambda _: show_placeholder("ОСТ 13-232-87")),
                        menu_card("ISO 4480-83", "В разработке", lambda _: show_placeholder("ISO 4480-83")),
                        menu_card("Оцилиндровка", "В разработке", lambda _: show_placeholder("Оцилиндровка")),
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
                    "Этот раздел пока не реализован. Табличные данные не подставляются до проверки источника.",
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
        table_view = ft.Row(spacing=8, expand=True, vertical_alignment=ft.CrossAxisAlignment.STRETCH)
        summary_view = ft.Column(spacing=12, expand=True)
        content_host = ft.Container(expand=True, content=table_view)

        def refresh_summary():
            summary_view.controls.clear()
            summary_view.controls.extend(
                [
                    ft.Text("Итоги расчёта", size=22, weight=ft.FontWeight.BOLD),
                    ft.Row(
                        controls=[
                            ft.Text("Количество брёвен", size=16),
                            ft.Container(expand=True),
                            ft.Text(total_count.value, size=17, weight=ft.FontWeight.BOLD),
                        ]
                    ),
                    ft.Row(
                        controls=[
                            ft.Text("Общая кубатура", size=16),
                            ft.Container(expand=True),
                            ft.Text("Не рассчитана", size=17, color=ORANGE, weight=ft.FontWeight.BOLD),
                        ]
                    ),
                    ft.Text(
                        "Для расчёта объёма необходимы проверенные значения таблицы ГОСТ 2708-75.",
                        size=13,
                        color=TEXT,
                    ),
                ]
            )

        def remove_item(index):
            if 0 <= index < len(current_items):
                current_items.pop(index)
                refresh_items()

        def refresh_items():
            items_column.controls.clear()
            if not current_items:
                items_column.controls.append(
                    ft.Container(
                        padding=16,
                        content=ft.Text("Нажмите на диаметр, чтобы добавить бревно.", color=TEXT),
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
                                    width=58,
                                    height=54,
                                    border_radius=10,
                                    bgcolor="#F5F6F6",
                                    alignment=ft.Alignment.CENTER,
                                    content=ft.Text(
                                        f"Ø{item['diameter']}",
                                        size=18,
                                        weight=ft.FontWeight.W_600,
                                        color=TEXT,
                                        no_wrap=True,
                                    ),
                                ),
                                ft.Row(
                                    spacing=5,
                                    expand=True,
                                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                    controls=[
                                        ft.Text(
                                            f"{item['length']:.1f} м",
                                            size=13,
                                            color=TEXT,
                                            no_wrap=True,
                                            max_lines=1,
                                        ),
                                        ft.Text("·", size=13, color=TEXT),
                                        ft.Text(
                                            f"{item['quantity']} шт.",
                                            size=13,
                                            color=TEXT,
                                            no_wrap=True,
                                            max_lines=1,
                                        ),
                                    ],
                                ),
                                ft.Column(
                                    spacing=0,
                                    horizontal_alignment=ft.CrossAxisAlignment.END,
                                    controls=[
                                        ft.Text("—", size=20, color=ORANGE, weight=ft.FontWeight.BOLD),
                                        ft.IconButton(
                                            ft.Icons.DELETE_OUTLINE,
                                            icon_color=TEXT,
                                            icon_size=20,
                                            tooltip="Удалить позицию",
                                            on_click=lambda e, i=index: remove_item(i),
                                        ),
                                    ],
                                ),
                            ],
                        ),
                    )
                )
            total_count.value = f"{sum(item['quantity'] for item in current_items)} шт."
            total_volume.value = "—"
            if active_tab["value"] == "summary":
                refresh_summary()
            page.update()

        def add_diameter(diameter):
            current_items.append(
                {
                    "diameter": diameter,
                    "length": selected_length["value"],
                    "quantity": 1,
                    "volume": None,
                    "display_volume": "—",
                    "status": "Ожидает проверенных данных таблицы ГОСТ",
                }
            )
            refresh_items()

        def choose_tab(tab_name):
            active_tab["value"] = tab_name
            is_table = tab_name == "table"
            content_host.content = table_view if is_table else summary_view
            table_tab.style = ft.ButtonStyle(
                color="white" if is_table else "#B8D4C8",
                bgcolor=GREEN,
                shape=ft.RoundedRectangleBorder(radius=0),
            )
            summary_tab.style = ft.ButtonStyle(
                color="white" if not is_table else "#B8D4C8",
                bgcolor=GREEN,
                shape=ft.RoundedRectangleBorder(radius=0),
            )
            if not is_table:
                refresh_summary()
            page.update()

        def open_length_picker(_):
            length_input = ft.TextField(
                label="Длина, м",
                value=f"{selected_length['value']:.1f}",
                keyboard_type=ft.KeyboardType.NUMBER,
                autofocus=True,
            )

            def set_length(_):
                try:
                    value = float(length_input.value.replace(",", "."))
                    if value <= 0:
                        raise ValueError
                except (TypeError, ValueError, AttributeError):
                    page.show_dialog(ft.SnackBar(content=ft.Text("Введите корректную длину больше нуля.")))
                    return
                selected_length["value"] = value
                length_button.content = ft.Row(
                    tight=True,
                    controls=[
                        ft.Icon(ft.Icons.STRAIGHTEN, color="white"),
                        ft.Text(f"ДЛИНА: {value:g}", color="white", weight=ft.FontWeight.BOLD),
                    ],
                )
                page.pop_dialog()
                page.update()

            def set_preset(value):
                length_input.value = f"{value:g}"
                set_length(None)

            dialog = ft.AlertDialog(
                modal=True,
                title=ft.Text("Выбор длины"),
                content=ft.Column(
                    tight=True,
                    controls=[
                        length_input,
                        ft.Row(
                            wrap=True,
                            controls=[
                                ft.TextButton(f"{preset:g} м", on_click=lambda e, v=preset: set_preset(v))
                                for preset in (4.0, 4.5, 5.0, 6.0, 6.5, 7.0, 8.0)
                            ],
                        ),
                    ],
                ),
                actions=[
                    ft.TextButton("Отмена", on_click=lambda _: page.pop_dialog()),
                    ft.FilledButton("Применить", on_click=set_length),
                ],
            )
            page.show_dialog(dialog)

        def save_gost(_):
            if not current_items:
                page.show_dialog(ft.SnackBar(content=ft.Text("Сначала добавьте брёвна.")))
                return
            save_calculation("ГОСТ 2708-75 · Таблица 1", current_items)
            page.show_dialog(ft.SnackBar(content=ft.Text("Расчёт сохранён на устройстве.")))

        diameter_grid = ft.GridView(
            expand=True,
            runs_count=2,
            spacing=5,
            run_spacing=5,
            child_aspect_ratio=1.0,
            controls=[
                ft.FilledButton(
                    content=ft.Text(str(diameter), size=22, no_wrap=True, max_lines=1, text_align=ft.TextAlign.CENTER),
                    height=58,
                    style=ft.ButtonStyle(
                        bgcolor="#E5E6E7",
                        color=TEXT,
                        padding=ft.Padding.symmetric(horizontal=2, vertical=4),
                        shape=ft.RoundedRectangleBorder(radius=5),
                        elevation=0,
                    ),
                    on_click=lambda e, d=diameter: add_diameter(d),
                )
                for diameter in DIAMETERS
            ],
        )
        list_panel = ft.Container(
            expand=3,
            padding=4,
            border=ft.Border.all(1, "#D8DADC"),
            border_radius=7,
            bgcolor="#FCFCFC",
            content=items_column,
        )
        keypad_panel = ft.Container(expand=2, padding=ft.Padding.only(left=2, right=2), content=diameter_grid)
        table_view.controls = [list_panel, keypad_panel]

        table_tab = ft.TextButton(
            "Таблица", expand=True, on_click=lambda _: choose_tab("table"),
            style=ft.ButtonStyle(color="white", bgcolor=GREEN),
        )
        summary_tab = ft.TextButton(
            "Итоги", expand=True, on_click=lambda _: choose_tab("summary"),
            style=ft.ButtonStyle(color="#B8D4C8", bgcolor=GREEN),
        )
        length_button = ft.FilledButton(
            content=ft.Row(
                tight=True,
                controls=[ft.Icon(ft.Icons.STRAIGHTEN, color="white"), ft.Text("ДЛИНА: 6", color="white", weight=ft.FontWeight.BOLD)],
            ),
            style=ft.ButtonStyle(bgcolor="#8C918F", color="white"),
            on_click=open_length_picker,
        )
        page.add(
            ft.Column(
                spacing=0,
                expand=True,
                controls=[
                    ft.Row(controls=[table_tab, summary_tab], spacing=0),
                    ft.Container(
                        padding=ft.Padding.symmetric(horizontal=12, vertical=7),
                        content=ft.Row(
                            controls=[ft.Icon(ft.Icons.TUNE, color="#85898C", size=25), total_volume, ft.Container(expand=True), total_count],
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                    ),
                    ft.Container(content=content_host, expand=True, padding=ft.Padding.symmetric(horizontal=8)),
                    ft.Container(
                        padding=ft.Padding.symmetric(horizontal=8, vertical=7),
                        content=ft.Row(
                            controls=[
                                ft.FilledButton(
                                    content=ft.Row(tight=True, controls=[ft.Icon(ft.Icons.SAVE, color="white"), ft.Text("Сохранить", color="white", weight=ft.FontWeight.BOLD)]),
                                    expand=True,
                                    style=ft.ButtonStyle(bgcolor=GREEN, color="white"),
                                    on_click=save_gost,
                                ),
                                length_button,
                            ],
                            spacing=7,
                        ),
                    ),
                ],
            )
        )
        refresh_items()
        page.update()

    def lumber_volume(item):
        thickness_m = Decimal(str(item["thickness_cm"])) / Decimal(100)
        width_m = Decimal(str(item["width_cm"])) / Decimal(100)
        length_m = Decimal(str(item["length_m"]))
        return thickness_m * width_m * length_m * int(item["quantity"])

    def show_lumber_calculator():
        page.controls.clear()
        page.appbar = ft.AppBar(
            leading=ft.IconButton(ft.Icons.ARROW_BACK, on_click=lambda _: show_home()),
            title=ft.Text("Расчёт #1\n(ПИЛОМАТЕРИАЛЫ)", size=18),
            bgcolor=GREEN,
            color="white",
        )

        summary_volume = ft.Text("0.0000 м³", size=28, color=ORANGE, weight=ft.FontWeight.BOLD)
        summary_details = ft.Text("0 шт. · 0.00 RUB.", size=16, color=TEXT)
        records = ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO, expand=True)
        price_currency = "RUB."

        def fmt(value, places=4):
            return f"{value:.{places}f}"

        def update_summary():
            total_volume = sum((lumber_volume(item) for item in lumber_items), Decimal(0))
            total_count = sum(int(item["quantity"]) for item in lumber_items)
            total_price = sum(
                (lumber_volume(item) * Decimal(str(item.get("price_per_m3", 0))) for item in lumber_items),
                Decimal(0),
            )
            summary_volume.value = f"{fmt(total_volume)} м³"
            summary_details.value = f"{total_count} шт. · {fmt(total_price, 2)} {price_currency}"

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

            page.show_dialog(
                ft.AlertDialog(
                    modal=True,
                    title=ft.Text(f"Позиция {index + 1}"),
                    actions=[
                        ft.TextButton("Изменить", on_click=edit),
                        ft.TextButton("Удалить", on_click=delete),
                    ],
                )
            )

        def refresh_records():
            records.controls.clear()
            for index, item in enumerate(lumber_items):
                volume = lumber_volume(item)
                price = volume * Decimal(str(item.get("price_per_m3", 0)))

                unit_volume = (
                    (Decimal(str(item["thickness_cm"])) / Decimal(100))
                    * (Decimal(str(item["width_cm"])) / Decimal(100))
                    * Decimal(str(item["length_m"]))
                )
                per_cubic = Decimal(1) / unit_volume if unit_volume > 0 else None

                unit = item.get("unit", "CM")
                scale = {
                    "MM": Decimal(10),
                    "CM": Decimal(1),
                    "M": Decimal("0.01"),
                }[unit]

                thickness = Decimal(str(item["thickness_cm"])) * scale
                width = Decimal(str(item["width_cm"])) * scale

                length_scale = {
                    "MM": Decimal(1000),
                    "CM": Decimal(100),
                    "M": Decimal(1),
                }[unit]

                length = Decimal(str(item["length_m"])) * length_scale
                dimension_unit = {"MM": "мм", "CM": "см", "M": "м"}[unit]

                records.controls.append(
                    ft.Container(
                        padding=ft.Padding.symmetric(horizontal=11, vertical=8),
                        border=ft.Border.all(1, "#E0E2E1"),
                        border_radius=16,
                        bgcolor="#FFFFFF",
                        content=ft.Column(
                            spacing=3,
                            controls=[
                                ft.Text(str(index + 1), size=12, color=TEXT),
                                ft.Row(
                                    spacing=5,
                                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                    controls=[
                                        ft.Text(
                                            f"{thickness.normalize():f} × {width.normalize():f} × {length.normalize():f} {dimension_unit}",
                                            size=16,
                                            color=GREEN,
                                            weight=ft.FontWeight.BOLD,
                                            expand=True,
                                            no_wrap=True,
                                            max_lines=1,
                                        ),
                                        ft.Container(
                                            padding=ft.Padding.symmetric(horizontal=8, vertical=6),
                                            border_radius=12,
                                            bgcolor="#F0F3F1",
                                            on_click=lambda e, i=index: open_lumber_editor(index=i, focus="quantity"),
                                            content=ft.Row(
                                                spacing=3,
                                                tight=True,
                                                controls=[
                                                    ft.Text(f"· {item['quantity']} шт.", color=GREEN, weight=ft.FontWeight.BOLD, no_wrap=True),
                                                    ft.Icon(ft.Icons.EDIT, size=15, color=GREEN),
                                                ],
                                            ),
                                        ),
                                        ft.IconButton(
                                            ft.Icons.CONTENT_COPY,
                                            icon_color=GREEN,
                                            tooltip="Дублировать",
                                            on_click=lambda e, i=index: open_lumber_editor(index=None, duplicate=i),
                                        ),
                                        ft.IconButton(
                                            ft.Icons.MORE_VERT,
                                            icon_color=TEXT,
                                            tooltip="Опции",
                                            on_click=lambda e, i=index: open_record_menu(i),
                                        ),
                                    ],
                                ),
                                ft.Row(
                                    controls=[
                                        ft.Text(
                                            f"В 1 м³: ≈ {int(per_cubic.to_integral_value(rounding='ROUND_HALF_UP'))} шт."
                                            if per_cubic is not None else "В 1 м³: —",
                                            size=13,
                                            color=TEXT,
                                        ),
                                        ft.Container(expand=True),
                                        ft.Column(
                                            spacing=0,
                                            horizontal_alignment=ft.CrossAxisAlignment.END,
                                            controls=[
                                                ft.Text(
                                                    f"{fmt(price, 2)} {price_currency}" if item.get("price_per_m3") else "",
                                                    size=13,
                                                    color=GREEN,
                                                    weight=ft.FontWeight.BOLD,
                                                ),
                                                ft.Text(f"{fmt(volume)} м³", size=20, color=ORANGE, weight=ft.FontWeight.BOLD),
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
                source = lumber_items[duplicate]
                data = dict(source)
                title = f"Новая позиция на основе №{duplicate + 1}"
            elif index is not None:
                data = dict(lumber_items[index])
                title = f"Позиция {index + 1}"
            else:
                data = {
                    "thickness_cm": 5.0,
                    "width_cm": 5.0,
                    "length_m": 6.0,
                    "quantity": 1,
                    "price_per_m3": 0,
                    "unit": "CM",
                }
                title = "Новый пиломатериал"

            field_order = [
                "thickness_cm",
                "width_cm",
                "length_m",
                "quantity",
                "price_per_m3",
            ]

            labels = {
                "thickness_cm": ("Толщина:", "см"),
                "width_cm": ("Ширина:", "см"),
                "length_m": ("Длина:", "см"),
                "quantity": ("Кол-во:", "шт."),
                "price_per_m3": ("Цена:", f"{price_currency}/м³"),
            }

            active_field = {"value": focus}
            unit_mode = {"value": data.get("unit", "CM")}

            fields = {}
            unit_texts = {}
            rows = []

            volume_label = ft.Text("0.0000", size=25, color=ORANGE, weight=ft.FontWeight.BOLD)
            price_label = ft.Text("0.00", size=19, color="#AAB1B1", weight=ft.FontWeight.BOLD)
            per_cubic_label = ft.Text("В 1 м³: ≈ 0 шт.", size=14, color=TEXT)

            def shown_value(key):
                value = Decimal(str(data[key]))

                if key in ("thickness_cm", "width_cm"):
                    if unit_mode["value"] == "MM":
                        value *= Decimal(10)
                    elif unit_mode["value"] == "M":
                        value /= Decimal(100)

                elif key == "length_m":
                    if unit_mode["value"] == "MM":
                        value *= Decimal(1000)
                    elif unit_mode["value"] == "CM":
                        value *= Decimal(100)

                return format(value.normalize(), "f")

            def update_editor_values():
                for key, field in fields.items():
                    field.value = shown_value(key) if key in data else ""

                temp = {
                    "thickness_cm": data["thickness_cm"],
                    "width_cm": data["width_cm"],
                    "length_m": data["length_m"],
                    "quantity": data["quantity"],
                }

                volume = lumber_volume(temp)
                volume_label.value = fmt(volume)
                price_label.value = fmt(
                    volume * Decimal(str(data.get("price_per_m3", 0))),
                    2,
                )

                unit_volume = (
                    Decimal(str(data["thickness_cm"])) / Decimal(100)
                    * Decimal(str(data["width_cm"])) / Decimal(100)
                    * Decimal(str(data["length_m"]))
                )

                per_cubic_label.value = (
                    f"В 1 м³: ≈ {int((Decimal(1) / unit_volume).to_integral_value(rounding='ROUND_HALF_UP'))} шт."
                    if unit_volume > 0 else "В 1 м³: —"
                )

                for key, field in fields.items():
                    field.value = shown_value(key)

            def select_field(key):
                active_field["value"] = key

                for name, container in field_rows.items():
                    container.bgcolor = "#FFFFFF"

                    if name == key:
                        container.border = ft.Border.all(2, ORANGE)
                    else:
                        container.border = ft.Border.all(1, "#E1E3E2")

                page.update()

            field_rows = {}

            for key in field_order:
                label, unit = labels[key]

                field = ft.TextField(
                    value=shown_value(key),
                    read_only=True,
                    border=ft.InputBorder.NONE,
                    text_size=16,
                    text_align=ft.TextAlign.START,
                    expand=True,
                    on_focus=lambda e, k=key: select_field(k),
                )

                fields[key] = field

                unit_control = ft.Text(
                    unit,
                    size=14,
                    color="#171A18",
                    width=68,
                )
                unit_texts[key] = unit_control

                row = ft.Container(
                    padding=ft.Padding.symmetric(horizontal=12, vertical=2),
                    border=ft.Border.all(1, "#E1E3E2"),
                    border_radius=12,
                    bgcolor="#FFFFFF",
                    on_click=lambda e, k=key: select_field(k),
                    content=ft.Row(
                        spacing=6,
                        controls=[
                            ft.Text(label, size=15, color="#171A18", width=112),
                            unit_control,
                            field,
                        ],
                    ),
                )

                field_rows[key] = row
                rows.append(row)

            def change_unit(unit):
                unit_mode["value"] = unit

                unit_label = {
                    "MM": "мм",
                    "CM": "см",
                    "M": "м",
                }[unit]

                for key in ("thickness_cm", "width_cm", "length_m"):
                    unit_texts[key].value = unit_label

                update_editor_values()
                page.update()

            def key_press(value):
                key = active_field["value"]
                current = shown_value(key)

                if value == "⌫":
                    current = current[:-1]

                elif value == ".":
                    if key == "quantity":
                        return

                    if "." not in current:
                        current = (current or "0") + "."

                else:
                    current = ("" if current == "0" else current) + value

                if current in ("", "."):
                    current = "0" if current == "" else "0."

                try:
                    number = Decimal(current)

                    if number < 0:
                        return

                    if key == "quantity":
                        number = int(number)

                    if key in ("thickness_cm", "width_cm"):
                        if unit_mode["value"] == "MM":
                            number /= Decimal(10)
                        elif unit_mode["value"] == "M":
                            number *= Decimal(100)

                    elif key == "length_m":
                        if unit_mode["value"] == "MM":
                            number /= Decimal(1000)
                        elif unit_mode["value"] == "CM":
                            number /= Decimal(100)

                    data[key] = number
                    update_editor_values()

                except (InvalidOperation, ValueError):
                    return

                page.update()

            keypad = ft.Column(
                spacing=5,
                controls=[
                    ft.Row(
                        spacing=5,
                        controls=[
                            ft.FilledButton(
                                unit,
                                expand=True,
                                height=44,
                                style=ft.ButtonStyle(
                                    bgcolor="#F0F2F1",
                                    color="#171A18",
                                ),
                                on_click=lambda e, u=unit: change_unit(u),
                            )
                            for unit in ("MM", "CM", "M")
                        ],
                    ),
                    *[
                        ft.Row(
                            spacing=5,
                            controls=[
                                ft.FilledButton(
                                    value,
                                    expand=True,
                                    height=48,
                                    style=ft.ButtonStyle(
                                        bgcolor="#F0F2F1",
                                        color=TEXT,
                                        text_style=ft.TextStyle(size=23),
                                    ),
                                    on_click=lambda e, v=value: key_press(v),
                                )
                                for value in trio
                            ],
                        )
                        for trio in (
                            ("1", "2", "3"),
                            ("4", "5", "6"),
                            ("7", "8", "9"),
                            ("⌫", "0", "."),
                        )
                    ],
                ],
            )

            def move_field(direction):
                current = field_order.index(active_field["value"])
                select_field(
                    field_order[
                        max(0, min(len(field_order) - 1, current + direction))
                    ]
                )

            def commit(_):
                try:
                    for key in ("thickness_cm", "width_cm", "length_m"):
                        if Decimal(str(data[key])) <= 0:
                            raise ValueError

                    if int(data["quantity"]) < 1:
                        raise ValueError

                    if Decimal(str(data.get("price_per_m3", 0))) < 0:
                        raise ValueError

                    data["unit"] = unit_mode["value"]

                except (ValueError, InvalidOperation, KeyError):
                    page.show_dialog(
                        ft.SnackBar(
                            content=ft.Text("Проверьте размеры, количество и цену.")
                        )
                    )
                    return

                if index is None:
                    lumber_items.append(dict(data))
                else:
                    lumber_items[index] = dict(data)

                page.pop_dialog()
                refresh_records()

            editor_content = ft.Column(
                tight=True,
                scroll=ft.ScrollMode.AUTO,
                spacing=5,
                controls=[
                    ft.Row(
                        controls=[
                            ft.Text(title, size=16, color=TEXT, expand=True),
                            ft.IconButton(ft.Icons.EDIT, icon_color=TEXT),
                            ft.IconButton(
                                ft.Icons.DELETE_OUTLINE,
                                icon_color=TEXT,
                                on_click=lambda _: clear_editor(),
                            ),
                        ],
                    ),
                    ft.Row(
                        controls=[volume_label, price_label],
                        spacing=12,
                    ),
                    *rows,
                    per_cubic_label,
                    keypad,
                    ft.Row(
                        controls=[
                            ft.IconButton(
                                ft.Icons.KEYBOARD_ARROW_UP,
                                on_click=lambda _: move_field(-1),
                            ),
                            ft.FilledButton(
                                "OK",
                                expand=True,
                                height=54,
                                style=ft.ButtonStyle(
                                    bgcolor="#E77C3B",
                                    color="white",
                                ),
                                on_click=commit,
                            ),
                            ft.IconButton(
                                ft.Icons.KEYBOARD_ARROW_DOWN,
                                on_click=lambda _: move_field(1),
                            ),
                        ],
                    ),
                ],
            )

            def clear_editor():
                if index is not None:
                    page.pop_dialog()
                    delete_lumber(index)

            dialog = ft.AlertDialog(
                modal=True,
                content=ft.Container(
                    width=520,
                    height=min((page.height or 800) * 0.88, 760),
                    content=editor_content,
                ),
                shape=ft.RoundedRectangleBorder(radius=24),
                inset_padding=ft.Padding.symmetric(horizontal=12, vertical=12),
            )

            page.show_dialog(dialog)

            initial_unit_label = {
                "MM": "мм",
                "CM": "см",
                "M": "м",
            }[unit_mode["value"]]

            for key in ("thickness_cm", "width_cm", "length_m"):
                unit_texts[key].value = initial_unit_label

            select_field(focus)
            update_editor_values()

        def add_lumber(_):
            open_lumber_editor()

        page.add(
            ft.Column(
                spacing=0,
                expand=True,
                controls=[
                    ft.Container(
                        padding=ft.Padding.symmetric(horizontal=18, vertical=10),
                        bgcolor="#FFFFFF",
                        content=ft.Column(
                            spacing=0,
                            controls=[summary_volume, summary_details],
                        ),
                    ),
                    ft.Container(
                        expand=True,
                        padding=ft.Padding.symmetric(horizontal=10, vertical=8),
                        bgcolor="#FFFFFF",
                        border_radius=12,
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
                                        "Добавить пиломатериал",
                                        color="white",
                                        weight=ft.FontWeight.BOLD,
                                        size=17,
                                    ),
                                ],
                            ),
                            expand=True,
                            height=62,
                            style=ft.ButtonStyle(
                                bgcolor="#E77C3B",
                                color="white",
                                shape=ft.RoundedRectangleBorder(radius=18),
                            ),
                            on_click=add_lumber,
                        ),
                    ),
                ],
            )
        )
        refresh_records()
        page.update()

    def show_history():
        page.controls.clear()
        page.appbar = ft.AppBar(
            leading=ft.IconButton(
                ft.Icons.ARROW_BACK,
                on_click=lambda _: show_home(),
            ),
            title=ft.Text("История расчётов"),
            bgcolor=GREEN,
            color="white",
        )

        rows = list_calculations()
        controls = []

        if not rows:
            controls.append(ft.Text("Сохранённых расчётов пока нет."))

        for row in rows:
            controls.append(
                ft.ListTile(
                    title=ft.Text(row["name"]),
                    subtitle=ft.Text(row["created_at"]),
                    trailing=ft.Text(f"{row['items_count']} поз."),
                )
            )

        page.add(
            ft.Container(
                padding=18,
                content=ft.Column(controls, spacing=8),
            )
        )
        page.update()

    show_home()


if __name__ == "__main__":
    ft.app(target=main)