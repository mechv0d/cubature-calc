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
                            lambda _: show_calculator(),
                        ),
                        menu_card("Пиломатериалы", "В разработке", lambda _: show_placeholder("Пиломатериалы")),
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

    def show_calculator():
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
        # A single expanding host prevents the hidden tab from reserving half
        # of the available height on Android.
        content_host = ft.Container(expand=True, content=table_view)

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
                        padding=ft.Padding.symmetric(horizontal=10, vertical=9),
                        border_radius=10,
                        bgcolor=PANEL,
                        content=ft.Row(
                            spacing=8,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            controls=[
                                ft.Container(
                                    width=66,
                                    height=58,
                                    border_radius=10,
                                    bgcolor="#F5F6F6",
                                    alignment=ft.Alignment.CENTER,
                                    content=ft.Text(
                                        f"Ø{item['diameter']}",
                                        size=19,
                                        weight=ft.FontWeight.W_600,
                                        color=TEXT,
                                    ),
                                ),
                                ft.Column(
                                    spacing=2,
                                    expand=True,
                                    controls=[
                                        ft.Text(
                                            f"{item['length']:.1f} м:  {item['quantity']} шт.",
                                            size=14,
                                            color=TEXT,
                                        ),
                                        ft.Text(f"#{index + 1}", size=11, color="#85898C"),
                                    ],
                                ),
                                ft.Column(
                                    spacing=0,
                                    horizontal_alignment=ft.CrossAxisAlignment.END,
                                    controls=[
                                        ft.Text("—", size=21, color=ORANGE, weight=ft.FontWeight.BOLD),
                                        ft.IconButton(
                                            ft.Icons.DELETE_OUTLINE,
                                            icon_color=TEXT,
                                            icon_size=21,
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
            # Table 1 has not yet been populated with verified source data.
            total_volume.value = "—"
            if active_tab["value"] == "summary":
                refresh_summary()
            page.update()

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
                        "Для расчёта объёма необходимо подключить проверенные значения таблицы ГОСТ 2708-75.",
                        size=13,
                        color=TEXT,
                    ),
                ]
            )

        def remove_item(index):
            if 0 <= index < len(current_items):
                current_items.pop(index)
                refresh_items()

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
                    page.snack_bar = ft.SnackBar(content=ft.Text("Введите корректную длину больше нуля."))
                    page.show_dialog(page.snack_bar)
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
                                ft.TextButton(
                                    f"{preset:g} м",
                                    on_click=lambda e, v=preset: set_preset(v),
                                )
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

            def set_preset(value):
                length_input.value = f"{value:g}"
                set_length(None)

            page.show_dialog(dialog)

        def save(_):
            if not current_items:
                page.snack_bar = ft.SnackBar(content=ft.Text("Сначала добавьте брёвна, нажав на диаметры."))
                page.show_dialog(page.snack_bar)
                return
            save_calculation("ГОСТ 2708-75 · Таблица 1", current_items)
            page.snack_bar = ft.SnackBar(content=ft.Text("Расчёт сохранён на устройстве."))
            page.show_dialog(page.snack_bar)

        # Diameter keypad: tapping a diameter immediately appends one log.
        diameter_grid = ft.GridView(
            expand=True,
            runs_count=2,
            spacing=5,
            run_spacing=5,
            child_aspect_ratio=1.0,
            controls=[
                ft.FilledButton(
                    content=ft.Text(
                        str(diameter),
                        size=22,
                        no_wrap=True,
                        max_lines=1,
                        text_align=ft.TextAlign.CENTER,
                    ),
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
        keypad_panel = ft.Container(
            expand=2,
            padding=ft.Padding.only(left=2, right=2),
            content=diameter_grid,
        )

        table_view.controls = [list_panel, keypad_panel]

        table_tab = ft.TextButton(
            "Таблица",
            expand=True,
            on_click=lambda _: choose_tab("table"),
            style=ft.ButtonStyle(color="white", bgcolor=GREEN),
        )
        summary_tab = ft.TextButton(
            "Итоги",
            expand=True,
            on_click=lambda _: choose_tab("summary"),
            style=ft.ButtonStyle(color="#B8D4C8", bgcolor=GREEN),
        )

        length_button = ft.FilledButton(
            content=ft.Row(
                tight=True,
                controls=[
                    ft.Icon(ft.Icons.STRAIGHTEN, color="white"),
                    ft.Text("ДЛИНА: 6", color="white", weight=ft.FontWeight.BOLD),
                ],
            ),
            style=ft.ButtonStyle(bgcolor="#8C918F", color="white"),
            on_click=open_length_picker,
        )
        save_button = ft.FilledButton(
            content=ft.Row(
                tight=True,
                controls=[
                    ft.Icon(ft.Icons.SAVE, color="white"),
                    ft.Text("Сохранить", color="white", weight=ft.FontWeight.BOLD),
                ],
            ),
            expand=True,
            style=ft.ButtonStyle(bgcolor=GREEN, color="white"),
            on_click=save,
        )

        page.add(
            ft.Column(
                spacing=0,
                expand=True,
                controls=[
                    ft.Row(
                        controls=[
                            table_tab,
                            summary_tab,
                        ],
                        spacing=0,
                    ),
                    ft.Container(
                        padding=ft.Padding.symmetric(horizontal=12, vertical=7),
                        content=ft.Row(
                            controls=[
                                ft.Icon(ft.Icons.TUNE, color="#85898C", size=25),
                                total_volume,
                                ft.Container(expand=True),
                                total_count,
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                    ),
                    ft.Container(content=content_host, expand=True, padding=ft.Padding.symmetric(horizontal=8)),
                    ft.Container(
                        padding=ft.Padding.symmetric(horizontal=8, vertical=7),
                        content=ft.Row(
                            controls=[
                                save_button,
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

    def show_history():
        page.controls.clear()
        page.appbar = ft.AppBar(
            leading=ft.IconButton(ft.Icons.ARROW_BACK, on_click=lambda _: show_home()),
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
        page.add(ft.Container(padding=18, content=ft.Column(controls, spacing=8)))
        page.update()

    show_home()


if __name__ == "__main__":
    ft.app(target=main)
