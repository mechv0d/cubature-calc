import math

import flet as ft

from app.storage import save_calculation

GREEN = "#176B4A"
ORANGE = "#E89A4E"
BG = "#F7F8F7"
PANEL = "#E8E9EA"
TEXT = "#62666A"

DIAMETERS = list(range(4, 101))


def cylinder_volume(diameter_cm: int, length_m: float, quantity: int = 1) -> float:
    """Объём оцилиндрованного бревна в м³ по формуле геометрического цилиндра."""
    radius_m = diameter_cm / 200
    return math.pi * radius_m**2 * length_m * quantity


def show_cylindering(page: ft.Page, show_home):
    """Отдельный экран расчёта оцилиндрованных брёвен."""

    items = []
    selected_diameter = {"value": None}
    selected_length = {"value": 7.0}
    active_tab = {"value": "table"}
    rounding_digits = {"value": 3}  # По умолчанию 0.000

    page.controls.clear()
    page.appbar = ft.AppBar(
        leading=ft.IconButton(
            ft.Icons.ARROW_BACK,
            on_click=lambda _: show_home(),
        ),
        title=ft.Text("Расчёт · Оцилиндровка", size=18),
        bgcolor=GREEN,
        color="white",
        center_title=True,
    )

    total_volume = ft.Text("0.000 м³", size=25, color=ORANGE,
                           weight=ft.FontWeight.BOLD)
    total_count = ft.Text("0 шт.", size=17, color=TEXT)
    records = ft.Column(spacing=7, scroll=ft.ScrollMode.AUTO, expand=True)
    summary = ft.Column(spacing=10, scroll=ft.ScrollMode.AUTO, expand=True)
    content_host = ft.Container(expand=True)
    diameter_buttons = {}

    def format_volume(value: float) -> str:
        return f"{value:.{rounding_digits['value']}f}"

    def item_volume(item) -> float:
        """Объём позиции, округлённый до выбранной точности."""
        return round(
            cylinder_volume(item["diameter"], item["length"], item["quantity"]),
            rounding_digits["value"],
        )

    def find_selected_item():
        diameter = selected_diameter["value"]
        length = selected_length["value"]
        if diameter is None:
            return None
        for item in items:
            if item["diameter"] == diameter and item["length"] == length:
                return item
        return None

    def update_totals():
        # Каждая позиция сначала округляется, затем значения складываются.
        volume = sum(item_volume(x) for x in items)
        count = sum(x["quantity"] for x in items)
        total_volume.value = f"{format_volume(volume)} м³"
        total_count.value = f"{count} шт."

    def refresh_summary():
        summary.controls.clear()
        summary.controls.append(
            ft.Text("Итоги по диаметрам", size=21,
                    weight=ft.FontWeight.BOLD)
        )
        grouped = {}
        for item in items:
            diameter = item["diameter"]
            grouped.setdefault(diameter, {"quantity": 0, "volume": 0.0})
            grouped[diameter]["quantity"] += item["quantity"]
            grouped[diameter]["volume"] += item_volume(item)

        if not grouped:
            summary.controls.append(
                ft.Text("Добавленных брёвен пока нет.", color=TEXT)
            )
        else:
            for diameter in sorted(grouped):
                data = grouped[diameter]
                summary.controls.append(
                    ft.Container(
                        padding=14,
                        border_radius=10,
                        bgcolor=PANEL,
                        content=ft.Row(
                            controls=[
                                ft.Text(f"Ø{diameter} см", size=17,
                                        weight=ft.FontWeight.BOLD),
                                ft.Container(expand=True),
                                ft.Text(f'{data["quantity"]} шт.',
                                        size=15, color=TEXT),
                                ft.Text(f'{format_volume(data["volume"])} м³',
                                        size=17, color=ORANGE,
                                        weight=ft.FontWeight.BOLD),
                            ],
                        ),
                    )
                )

    def refresh_records():
        records.controls.clear()

        if not items:
            records.controls.append(
                ft.Container(
                    padding=16,
                    content=ft.Text(
                        "Выберите диаметр справа, чтобы добавить бревно.",
                        color=TEXT,
                    ),
                )
            )

        for index, item in enumerate(items):
            volume = item_volume(item)
            is_selected = item["diameter"] == selected_diameter["value"]

            records.controls.append(
                ft.Container(
                    padding=10,
                    border_radius=10,
                    bgcolor=PANEL,
                    border=ft.Border.all(
                        2 if is_selected else 0,
                        GREEN if is_selected else PANEL,
                    ),
                    content=ft.Column(
                        spacing=5,
                        controls=[
                            ft.Row(
                                spacing=8,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                controls=[
                                    ft.Container(
                                        width=66,
                                        height=48,
                                        border_radius=10,
                                        bgcolor="#F5F6F6",
                                        alignment=ft.Alignment.CENTER,
                                        content=ft.Text(
                                            f'Ø{item["diameter"]}',
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
                                                f'{item["length"]:g} м',
                                                size=15,
                                                color=TEXT,
                                            ),
                                            ft.Text(
                                                f'{item["quantity"]} шт. · #{index + 1}',
                                                size=13,
                                                color=TEXT,
                                            ),
                                        ],
                                    ),
                                    ft.IconButton(
                                        ft.Icons.DELETE_OUTLINE,
                                        icon_color=TEXT,
                                        tooltip="Удалить позицию",
                                        on_click=lambda e, i=index: delete_item(i),
                                    ),
                                ],
                            ),
                            ft.Text(
                                f"{format_volume(volume)} м³",
                                size=21,
                                color=ORANGE,
                                weight=ft.FontWeight.BOLD,
                            ),
                        ],
                    ),
                )
            )

        update_totals()

        if active_tab["value"] == "summary":
            refresh_summary()

        refresh_diameter_buttons()
        page.update()

    def refresh_diameter_buttons():
        for diameter, button in diameter_buttons.items():
            selected = diameter == selected_diameter["value"]
            button.style = ft.ButtonStyle(
                bgcolor=GREEN if selected else "#E5E6E7",
                color="white" if selected else TEXT,
                shape=ft.RoundedRectangleBorder(radius=5),
                padding=ft.Padding.symmetric(horizontal=2, vertical=4),
            )

    def add_diameter(diameter):
        selected_diameter["value"] = diameter
        existing = find_selected_item()
        if existing:
            existing["quantity"] += 1
        else:
            items.append({
                "diameter": diameter,
                "length": selected_length["value"],
                "quantity": 1,
            })
        refresh_records()

    def change_rounding(e):
        value = e.control.value
        if not value:
            return
        rounding_digits["value"] = len(value.split(".", 1)[1])
        refresh_records()

    def delete_item(index):
        if 0 <= index < len(items):
            items.pop(index)
            refresh_records()

    def choose_tab(tab):
        active_tab["value"] = tab
        is_table = tab == "table"
        content_host.content = table_view if is_table else summary
        table_tab.style = ft.ButtonStyle(
            bgcolor=GREEN,
            color="white" if is_table else "#B8D4C8",
            shape=ft.RoundedRectangleBorder(radius=0),
        )
        summary_tab.style = ft.ButtonStyle(
            bgcolor=GREEN,
            color="white" if not is_table else "#B8D4C8",
            shape=ft.RoundedRectangleBorder(radius=0),
        )
        if not is_table:
            refresh_summary()
        page.update()

    def open_length_picker(_):
        length_input = ft.TextField(
            label="Длина, м",
            value=f'{selected_length["value"]:g}',
            keyboard_type=ft.KeyboardType.NUMBER,
            autofocus=True,
        )

        def apply_length(_):
            try:
                value = float(length_input.value.replace(",", "."))
                if not math.isfinite(value) or value <= 0:
                    raise ValueError
            except (ValueError, TypeError, AttributeError):
                page.show_dialog(ft.SnackBar(
                    content=ft.Text("Введите длину больше нуля.")
                ))
                return

            selected_length["value"] = value
            # Существующие позиции не меняем: новая длина применяется
            # только к брёвнам, добавленным после её выбора.
            length_button.content = ft.Row(
                tight=True,
                controls=[
                    ft.Icon(ft.Icons.STRAIGHTEN, color="white"),
                    ft.Text(f"ДЛИНА: {value:g}", color="white",
                            weight=ft.FontWeight.BOLD),
                ],
            )
            page.pop_dialog()
            page.update()

        page.show_dialog(ft.AlertDialog(
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
                                f"{v:g} м",
                                on_click=lambda e, n=v: set_preset(n),
                            )
                            for v in (4.0, 4.5, 5.0, 6.0, 6.5, 7.0, 8.0)
                        ],
                    ),
                ],
            ),
            actions=[
                ft.TextButton("Отмена",
                              on_click=lambda _: page.pop_dialog()),
                ft.FilledButton("Применить", on_click=apply_length),
            ],
        ))

        def set_preset(value):
            length_input.value = f"{value:g}"
            apply_length(None)

    def save_current(_):
        if not items:
            page.show_dialog(ft.SnackBar(
                content=ft.Text("Сначала добавьте хотя бы одно бревно.")
            ))
            return
        save_calculation("Оцилиндровка", [
            {
                "diameter_cm": item["diameter"],
                "length_m": item["length"],
                "quantity": item["quantity"],
                "volume_m3": round(
                    cylinder_volume(
                        item["diameter"], item["length"], item["quantity"]
                    ),
                    rounding_digits["value"],
                ),
            }
            for item in items
        ])
        page.show_dialog(ft.SnackBar(
            content=ft.Text("Расчёт сохранён в историю.")
        ))

    diameter_grid = ft.GridView(
        expand=True,
        runs_count=2,
        spacing=5,
        run_spacing=5,
        child_aspect_ratio=1.0,
        controls=[],
    )

    for diameter in DIAMETERS:
        button = ft.FilledButton(
            content=ft.Text(str(diameter), size=22,
                            weight=ft.FontWeight.W_600),
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
        diameter_buttons[diameter] = button
        diameter_grid.controls.append(button)

    rounding_selector = ft.Dropdown(
        label="Округление",
        value="0.000",
        width=150,
        dense=True,
        text_size=15,
        options=[
            ft.dropdown.Option("0.0"),
            ft.dropdown.Option("0.00"),
            ft.dropdown.Option("0.000"),
            ft.dropdown.Option("0.0000"),
            ft.dropdown.Option("0.00000"),
            ft.dropdown.Option("0.000000"),
        ],
        on_select=change_rounding,
    )

    table_view = ft.Row(
        spacing=7,
        expand=True,
        vertical_alignment=ft.CrossAxisAlignment.STRETCH,
        controls=[
            ft.Container(
                expand=3,
                padding=5,
                border=ft.Border.all(1, "#D8DADC"),
                border_radius=7,
                bgcolor="#FCFCFC",
                content=records,
            ),
            ft.Container(
                expand=2,
                content=ft.Column(
                    spacing=5,
                    expand=True,
                    controls=[rounding_selector, diameter_grid],
                ),
            ),
        ],
    )

    table_tab = ft.TextButton(
        "Таблица",
        expand=True,
        on_click=lambda _: choose_tab("table"),
        style=ft.ButtonStyle(bgcolor=GREEN, color="white"),
    )
    summary_tab = ft.TextButton(
        "Итоги",
        expand=True,
        on_click=lambda _: choose_tab("summary"),
        style=ft.ButtonStyle(bgcolor=GREEN, color="#B8D4C8"),
    )

    length_button = ft.FilledButton(
        content=ft.Row(
            tight=True,
            controls=[
                ft.Icon(ft.Icons.STRAIGHTEN, color="white"),
                ft.Text("ДЛИНА: 7", color="white",
                        weight=ft.FontWeight.BOLD),
            ],
        ),
        style=ft.ButtonStyle(bgcolor="#8C918F", color="white"),
        on_click=open_length_picker,
    )

    content_host.content = table_view
    page.add(ft.Column(
        spacing=0,
        expand=True,
        controls=[
            ft.Row(controls=[table_tab, summary_tab], spacing=0),
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
            ft.Container(
                content=content_host,
                expand=True,
                padding=ft.Padding.symmetric(horizontal=8),
            ),
            ft.Container(
                padding=ft.Padding.symmetric(horizontal=8, vertical=7),
                content=ft.Row(
                    controls=[
                        ft.FilledButton(
                            content=ft.Row(
                                tight=True,
                                controls=[
                                    ft.Icon(ft.Icons.SAVE, color="white"),
                                    ft.Text("Сохранить", color="white",
                                            weight=ft.FontWeight.BOLD),
                                ],
                            ),
                            expand=True,
                            height=54,
                            on_click=save_current,
                            style=ft.ButtonStyle(
                                bgcolor=GREEN, color="white",
                            ),
                        ),
                        length_button,
                    ],
                    spacing=7,
                ),
            ),
        ],
    ))
    refresh_records()