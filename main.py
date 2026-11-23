import flet as ft
from app.storage import init_db, list_calculations, save_calculation

GREEN = "#176B4A"
ORANGE = "#E89A4E"
BG = "#F7F8F7"


def main(page: ft.Page):
    init_db()
    page.title = "Расчёт кубатуры"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = BG
    page.padding = 0
    page.window_min_width = 360
    page.window_min_height = 640

    current_items = []
    selected_section = {"value": "home"}

    def show_home():
        selected_section["value"] = "home"
        page.controls.clear()
        page.appbar = ft.AppBar(
            title=ft.Text("Расчёт кубатуры", weight=ft.FontWeight.W_600),
            bgcolor=GREEN, color="white", center_title=True
        )
        page.add(
            ft.Container(
                padding=18,
                content=ft.Column(
                    spacing=12,
                    controls=[
                        ft.Container(
                            padding=18, border_radius=20,
                            bgcolor="#E5F0E9",
                            content=ft.Text("Автономный режим · данные хранятся на устройстве",
                                            color="#3E5549", size=15)
                        ),
                        menu_card("ГОСТ 2708-75 · Таблица 1", "Расчёт круглых лесоматериалов", lambda _: show_calculator()),
                        menu_card("Пиломатериалы", "В разработке", lambda _: show_placeholder("Пиломатериалы")),
                        menu_card("ОСТ 13-232-87", "В разработке", lambda _: show_placeholder("ОСТ 13-232-87")),
                        menu_card("ISO 4480-83", "В разработке", lambda _: show_placeholder("ISO 4480-83")),
                        menu_card("Оцилиндровка", "В разработке", lambda _: show_placeholder("Оцилиндровка")),
                        ft.OutlinedButton("История расчётов", icon=ft.Icons.HISTORY, on_click=lambda _: show_history()),
                    ]
                )
            )
        )
        page.update()

    def menu_card(title, subtitle, action):
        return ft.Card(
            elevation=0,
            color="#F0F1EF",
            content=ft.ListTile(
                title=ft.Text(title, size=19, weight=ft.FontWeight.W_600),
                subtitle=ft.Text(subtitle, size=12),
                trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT),
                on_click=action,
                content_padding=ft.Padding.symmetric(horizontal=16, vertical=8),
            )
        )

    def show_placeholder(title):
        page.controls.clear()
        page.appbar = ft.AppBar(
            leading=ft.IconButton(ft.Icons.ARROW_BACK, on_click=lambda _: show_home()),
            title=ft.Text(title), bgcolor=GREEN, color="white"
        )
        page.add(ft.Container(padding=24, content=ft.Text(
            "Этот раздел пока не реализован. Табличные данные не подставляются до проверки источника.",
            size=16
        )))
        page.update()

    def show_calculator():
        selected_section["value"] = "gost"
        page.controls.clear()
        page.appbar = ft.AppBar(
            leading=ft.IconButton(ft.Icons.ARROW_BACK, on_click=lambda _: show_home()),
            title=ft.Text("ГОСТ 2708-75 · Табл. 1"),
            bgcolor=GREEN, color="white"
        )
        diameter = ft.TextField(label="Диаметр, см", value="20", keyboard_type=ft.KeyboardType.NUMBER, width=145)
        length = ft.TextField(label="Длина, м", value="6.0", keyboard_type=ft.KeyboardType.NUMBER, width=145)
        quantity = ft.TextField(label="Количество, шт.", value="1", keyboard_type=ft.KeyboardType.NUMBER, width=145)
        result_text = ft.Text("Кубатура: —", size=20, color=ORANGE, weight=ft.FontWeight.BOLD)
        items_column = ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO, expand=True)

        def refresh_items():
            items_column.controls.clear()
            if not current_items:
                items_column.controls.append(ft.Text("Позиции пока не добавлены.", color="#777777"))
            for idx, item in enumerate(current_items, start=1):
                items_column.controls.append(
                    ft.Container(
                        padding=12, border_radius=12, bgcolor="#E9EAE8",
                        content=ft.Row([
                            ft.Column([
                                ft.Text(f"Ø{item['diameter']} · {item['length']} м × {item['quantity']} шт.", weight=ft.FontWeight.W_600),
                                ft.Text(item["status"], size=12, color="#666666"),
                            ], expand=True),
                            ft.Text(item["display_volume"], size=18, color=ORANGE, weight=ft.FontWeight.BOLD),
                            ft.IconButton(ft.Icons.DELETE_OUTLINE, on_click=lambda e, i=idx-1: remove_item(i))
                        ])
                    )
                )
            page.update()

        def remove_item(index):
            current_items.pop(index)
            refresh_items()

        def add_item(_):
            try:
                d = int(diameter.value)
                l = float(length.value.replace(",", "."))
                q = int(quantity.value)
                if d <= 0 or l <= 0 or q <= 0:
                    raise ValueError()
            except (TypeError, ValueError):
                page.snack_bar = ft.SnackBar(ft.Text("Проверьте диаметр, длину и количество."))
                page.snack_bar.open = True
                page.update()
                return

            # Do not invent ГОСТ table values. Until a verified table is supplied,
            # this app records the inputs but leaves volume uncalculated.
            current_items.append({
                "diameter": d, "length": l, "quantity": q,
                "volume": None, "display_volume": "—",
                "status": "Нет проверенной таблицы ГОСТ для этой позиции"
            })
            refresh_items()

        def save(_):
            if not current_items:
                page.snack_bar = ft.SnackBar(ft.Text("Сначала добавьте хотя бы одну позицию."))
                page.snack_bar.open = True
                page.update()
                return
            save_calculation("ГОСТ 2708-75 · Таблица 1", current_items)
            page.snack_bar = ft.SnackBar(ft.Text("Расчёт сохранён на устройстве."))
            page.snack_bar.open = True
            page.update()

        page.add(
            ft.Container(
                padding=16, expand=True,
                content=ft.Column([
                    ft.Text("Добавить позицию", size=20, weight=ft.FontWeight.BOLD),
                    ft.Row([diameter, length], wrap=True),
                    ft.Row([quantity, ft.FilledButton("Добавить", icon=ft.Icons.ADD, on_click=add_item)], wrap=True),
                    ft.Divider(),
                    ft.Row([ft.Text("Позиции", size=19, weight=ft.FontWeight.BOLD), ft.Container(expand=True), result_text]),
                    items_column,
                    ft.FilledButton("Сохранить расчёт", icon=ft.Icons.SAVE, on_click=save,
                                    style=ft.ButtonStyle(bgcolor=GREEN, color="white")),
                    ft.Text("Важно: объёмы появятся после подключения и проверки официальной таблицы. Примерные значения не используются.",
                            size=12, color="#777777")
                ], expand=True)
            )
        )
        refresh_items()
        page.update()

    def show_history():
        page.controls.clear()
        page.appbar = ft.AppBar(
            leading=ft.IconButton(ft.Icons.ARROW_BACK, on_click=lambda _: show_home()),
            title=ft.Text("История расчётов"), bgcolor=GREEN, color="white"
        )
        rows = list_calculations()
        controls = []
        if not rows:
            controls.append(ft.Text("Сохранённых расчётов пока нет."))
        for row in rows:
            controls.append(ft.ListTile(
                title=ft.Text(row["name"]),
                subtitle=ft.Text(row["created_at"]),
                trailing=ft.Text(f"{row['items_count']} поз."),
            ))
        page.add(ft.Container(padding=18, content=ft.Column(controls, spacing=8)))
        page.update()

    show_home()


if __name__ == "__main__":
    ft.app(target=main)
