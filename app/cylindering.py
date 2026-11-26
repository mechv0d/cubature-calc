import math
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

import flet as ft

from app.screen_utils import (
    keep_screen_awake,
    load_screen_state,
    save_screen_state,
    setup_haptic,
    vibrate,
)
from app.storage import list_parties, save_calculation
from app.summary import (
    TAB_BAR_HEIGHT,
    CalculationSummary,
    ask_quantity,
    calc_tab_bar,
    calc_tab_style,
    default_settings,
    load_settings,
    price_for_diameter,
)

GREEN = "#176B4A"
ORANGE = "#E89A4E"
BG = "#F7F8F7"
PANEL = "#E8E9EA"
TEXT = "#62666A"

DIAMETERS = list(range(3, 121))
ROUNDING_OPTIONS = ("0.0", "0.00", "0.000", "0.0000", "0.00000", "0.000000")


def diameter_grid_columns(page):
    """Return 2 columns on phones and never more than 4 columns."""
    width = getattr(page, "width", 0) or 0
    if width >= 1000:
        return 4
    if width >= 700:
        return 3
    return 2


def cylinder_volume(diameter_cm: int, length_m: float, quantity: int = 1) -> float:
    """Объём оцилиндрованного бревна в м³ по формуле геометрического цилиндра."""
    radius_m = diameter_cm / 200
    return math.pi * radius_m**2 * length_m * quantity


def round_volume(value, digits: int) -> Decimal:
    """Округлить объём до указанного количества знаков (половина — вверх)."""
    quantum = Decimal(1).scaleb(-digits)
    return Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP)


def show_cylindering(
    page: ft.Page, show_home, create_party=None, navigator=None
):
    """Отдельный экран расчёта оцилиндрованных брёвен."""

    keep_screen_awake(page)
    setup_haptic(page)

    if navigator is not None:
        navigator.push(
            "/cylindering",
            lambda: show_cylindering(
                page, show_home, create_party, navigator
            ),
        )

    # Restore the draft saved on the previous run (app/phone restart).
    draft = load_screen_state("cylindering")
    items = list(draft.get("items", []))
    selected_diameter = {"value": draft.get("diameter")}
    selected_length = {"value": float(draft.get("length", 7.0))}
    active_tab = {"value": draft.get("tab", "table")}
    try:
        saved_digits = int(draft.get("rounding", 3))
    except (TypeError, ValueError):
        saved_digits = 3
    rounding_digits = {"value": min(max(saved_digits, 1), 6)}

    saved_settings = draft.get("settings") or {}
    if not isinstance(saved_settings, dict):
        saved_settings = {}
    if not saved_settings:
        saved_settings = load_screen_state("cylindering_settings")
    settings = load_settings(saved_settings)

    # Calculation numbers follow the saved parties of this type.
    calculation_number = sum(
        1 for party in list_parties() if party["type"] == "Оцилиндровка"
    ) + 1

    def save_state():
        save_screen_state("cylindering", {
            "items": items,
            "diameter": selected_diameter["value"],
            "length": selected_length["value"],
            "tab": active_tab["value"],
            "rounding": rounding_digits["value"],
            "settings": settings,
        })
        save_screen_state("cylindering_settings", settings)

    page.controls.clear()
    page.navigation_bar = None

    total_volume = ft.Text("0.000 м³", size=25, color=ORANGE,
                           weight=ft.FontWeight.BOLD)
    total_count = ft.Text("0 шт.", size=17, color=TEXT)
    records = ft.Column(spacing=7, scroll=ft.ScrollMode.AUTO, expand=True)
    content_host = ft.Container(expand=True)
    diameter_buttons = {}

    def format_volume(value) -> str:
        return f"{value:.{rounding_digits['value']}f}"

    def item_volume(item) -> Decimal:
        """Объём позиции, округлённый до выбранной точности."""
        return round_volume(
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

    def summary_items():
        """Items in the shape expected by the shared «Итоги» component."""
        return [
            {
                "diameter": item["diameter"],
                "length": item["length"],
                "quantity": item["quantity"],
                "volume": item_volume(item),
                "display_volume": format_volume(item_volume(item)),
            }
            for item in items
        ]

    def confirm_delete_records():
        def delete(_):
            items.clear()
            selected_diameter["value"] = None
            save_state()
            page.pop_dialog()
            update_totals()
            refresh_records()
            refresh_diameter_buttons()
            if active_tab["value"] == "summary":
                summary.refresh()
            page.update()

        page.show_dialog(ft.AlertDialog(
            modal=True,
            title=ft.Text("Удалить записи?"),
            content=ft.Text(
                "Все добавленные брёвна будут удалены. "
                "Настройки расчёта сохранятся."
            ),
            actions=[
                ft.TextButton("Отмена", on_click=lambda _: page.pop_dialog()),
                ft.TextButton("Удалить", on_click=delete),
            ],
        ))

    def confirm_clear_records():
        def clear(_):
            items.clear()
            selected_diameter["value"] = None
            settings.clear()
            settings.update(default_settings())
            summary.digits = 3
            rounding_digits["value"] = 3
            rounding_selector.value = "0.000"
            save_state()
            page.pop_dialog()
            update_totals()
            refresh_records()
            refresh_diameter_buttons()
            if active_tab["value"] == "summary":
                summary.refresh()
            page.update()

        page.show_dialog(ft.AlertDialog(
            modal=True,
            title=ft.Text("Очистить расчёт?"),
            content=ft.Text(
                "Все добавленные брёвна будут удалены, "
                "а настройки расчёта вернутся к стандартным."
            ),
            actions=[
                ft.TextButton("Отмена", on_click=lambda _: page.pop_dialog()),
                ft.TextButton("Очистить", on_click=clear),
            ],
        ))

    def open_quantity_dialog(index):
        if not 0 <= index < len(items):
            return
        item = items[index]
        label = f"Ø{item['diameter']} {item['length']:g}м"
        def apply(quantity):
            item["quantity"] = quantity
            refresh_records()

        ask_quantity(page, label, item["quantity"], apply)

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
                    on_click=lambda e, i=index: open_quantity_dialog(i),
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
                                        width=46,
                                        border_radius=10,
                                        bgcolor="#F5F6F6",
                                        alignment=ft.Alignment.CENTER,
                                        padding=ft.Padding.symmetric(
                                            horizontal=0, vertical=8
                                        ),
                                        content=ft.Text(
                                            f'Ø{item["diameter"]}',
                                            size=16,
                                            weight=ft.FontWeight.W_600,
                                            color=TEXT,
                                            no_wrap=True,
                                            max_lines=1,
                                            overflow=ft.TextOverflow.ELLIPSIS,
                                        ),
                                    ),
                                    ft.Column(
                                        spacing=1,
                                        expand=True,
                                        controls=[
                                            ft.Text(
                                                f'{item["length"]:g} м',
                                                size=13,
                                                color=TEXT,
                                                no_wrap=True,
                                                overflow=ft.TextOverflow.ELLIPSIS,
                                            ),
                                            ft.Text(
                                                f'{item["quantity"]} шт.',
                                                size=13,
                                                color=TEXT,
                                                no_wrap=True,
                                                overflow=ft.TextOverflow.ELLIPSIS,
                                            ),
                                        ],
                                    ),
                                    ft.IconButton(
                                        ft.Icons.DELETE_OUTLINE,
                                        icon_color=TEXT,
                                        icon_size=20,
                                        tooltip="Удалить позицию",
                                        on_click=lambda e, i=index: delete_item(i),
                                    ),
                                ],
                            ),
                            ft.Text(
                                f"{format_volume(volume)} м³",
                                size=18,
                                color=ORANGE,
                                weight=ft.FontWeight.BOLD,
                                no_wrap=True,
                                max_lines=1,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                        ],
                    ),
                )
            )

        update_totals()

        if active_tab["value"] == "summary":
            summary.refresh()

        refresh_diameter_buttons()
        save_state()
        page.update()

    def refresh_diameter_buttons():
        mode = settings["diameter_filter"]
        diameter_grid.controls.clear()
        for diameter in DIAMETERS:
            if mode == "even" and diameter % 2:
                continue
            if mode == "odd" and diameter % 2 == 0:
                continue
            diameter_grid.controls.append(diameter_buttons[diameter])
        for diameter, button in diameter_buttons.items():
            selected = diameter == selected_diameter["value"]
            button.style = ft.ButtonStyle(
                bgcolor=GREEN if selected else "#E5E6E7",
                color="white" if selected else TEXT,
                shape=ft.RoundedRectangleBorder(radius=0),
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
        vibrate(page)

    def change_rounding(e):
        value = e.control.value
        if not value:
            return
        rounding_digits["value"] = len(value.split(".", 1)[1])
        summary.digits = rounding_digits["value"]
        refresh_records()

    def delete_item(index):
        if 0 <= index < len(items):
            items.pop(index)
            refresh_records()

    def choose_tab(tab):
        active_tab["value"] = tab
        is_table = tab == "table"
        content_host.content = table_view if is_table else summary.view
        bottom_host.content = table_actions if is_table else summary.actions
        volume_row.visible = is_table
        summary.totals.visible = not is_table
        if is_table:
            summary.totals.content = None
        table_tab.style = calc_tab_style(GREEN, is_table)
        summary_tab.style = calc_tab_style(GREEN, not is_table)
        if not is_table:
            summary.refresh()
        save_state()
        page.update()

    def back_from_summary():
        """«Назад» с «Итогов» возвращает к таблице расчёта."""
        if active_tab["value"] != "summary":
            return False
        choose_tab("table")
        return True

    if navigator is not None:
        navigator.on_screen_back(back_from_summary)

    def open_length_picker(_):
        length_input = ft.TextField(
            label="Длина, м",
            value=f'{selected_length["value"]:g}',
            keyboard_type=ft.KeyboardType.NUMBER,
            autofocus=True,
        )
        length_error = ft.Text(
            "", size=12, color="#B3261E", visible=False,
        )

        def apply_length(_):
            try:
                value = float(length_input.value.replace(",", "."))
                if not math.isfinite(value) or value <= 0:
                    raise ValueError
            except (ValueError, TypeError, AttributeError):
                length_error.value = "Введите длину больше нуля."
                length_error.visible = True
                page.update()
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
            save_state()
            page.pop_dialog()
            page.update()

        page.show_dialog(ft.AlertDialog(
            modal=True,
            title=ft.Text("Выбор длины"),
            content=ft.Column(
                tight=True,
                controls=[
                    length_input,
                    length_error,
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

    def party_payload():
        payload = []
        for item in items:
            volume = item_volume(item)
            price, price_range = price_for_diameter(
                settings, item["diameter"]
            )
            payload.append({
                "diameter_cm": item["diameter"],
                "length_m": item["length"],
                "quantity": item["quantity"],
                "volume_m3": float(volume),
                "price_per_m3": str(price) if price is not None else "0",
                "range_from": price_range["from"] if price_range else None,
                "range_to": price_range["to"] if price_range else None,
                "species": settings["species"],
                "calc_type": settings["calc_type"],
                "cost": str(volume * price) if price is not None else "0",
            })
        return payload

    def save_current(_):
        if not items:
            page.show_dialog(ft.SnackBar(
                content=ft.Text("Сначала добавьте хотя бы одно бревно.")
            ))
            return
        if create_party:
            now = datetime.now()
            create_party(
                "Оцилиндровка",
                f"ОЦБ #{calculation_number} "
                f"({now.day}.{now.month:02d})",
                party_payload(),
                preset_counterparty=settings["counterparty"] or None,
                preset_description=(
                    f"Порода: {settings['species']}. "
                    f"Тип расчёта: {settings['calc_type']}."
                ),
            )
            return
        save_calculation("Оцилиндровка", party_payload())
        page.show_dialog(ft.SnackBar(
            content=ft.Text("Расчёт сохранён в историю.")
        ))

    def apply_settings_changes():
        refresh_diameter_buttons()
        refresh_records()

    summary = CalculationSummary(
        page,
        settings=settings,
        number=calculation_number,
        title=f"ОЦБ #{calculation_number} (Оцилиндровка)",
        get_items=summary_items,
        digits=rounding_digits["value"],
        on_save=save_current,
        on_settings_changed=apply_settings_changes,
        excel_note="Excel-таблица · Оцилиндровка",
    )

    page.appbar = ft.AppBar(
        leading=ft.IconButton(
            ft.Icons.ARROW_BACK,
            on_click=lambda _: show_home(),
        ),
        title=ft.Text("Расчёт · Оцилиндровка", size=18),
        bgcolor=GREEN,
        color="white",
        center_title=True,
        actions=[
            ft.PopupMenuButton(
                icon=ft.Icons.MORE_VERT,
                tooltip="Меню",
                items=[
                    ft.PopupMenuItem(
                        content=ft.Text("Настройки расчёта"),
                        on_click=lambda _: summary.open_settings(_),
                    ),
                    ft.PopupMenuItem(
                        content=ft.Text("Удалить записи"),
                        on_click=lambda _: confirm_delete_records(),
                    ),
                    ft.PopupMenuItem(
                        content=ft.Text("Очистить расчёт"),
                        on_click=lambda _: confirm_clear_records(),
                    ),
                ],
            ),
        ],
    )

    diameter_grid = ft.GridView(
        expand=True,
        runs_count=diameter_grid_columns(page),
        spacing=5,
        run_spacing=5,
        child_aspect_ratio=1.08,
        controls=[],
    )

    for diameter in DIAMETERS:
        button = ft.FilledButton(
            content=ft.Text(str(diameter), size=22,
                            weight=ft.FontWeight.W_600),
            height=72,
            style=ft.ButtonStyle(
                bgcolor="#E5E6E7",
                color=TEXT,
                padding=ft.Padding.symmetric(horizontal=2, vertical=4),
                shape=ft.RoundedRectangleBorder(radius=0),
                elevation=0,
            ),
            on_click=lambda e, d=diameter: add_diameter(d),
        )
        diameter_buttons[diameter] = button
        diameter_grid.controls.append(button)

    rounding_selector = ft.Dropdown(
        label="Округление",
        value="0." + "0" * rounding_digits["value"],
        width=150,
        dense=True,
        text_size=15,
        options=[ft.dropdown.Option(option) for option in ROUNDING_OPTIONS],
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
        height=TAB_BAR_HEIGHT,
        on_click=lambda _: choose_tab("table"),
        style=calc_tab_style(GREEN, True),
    )
    summary_tab = ft.TextButton(
        "Итоги",
        expand=True,
        height=TAB_BAR_HEIGHT,
        on_click=lambda _: choose_tab("summary"),
        style=calc_tab_style(GREEN, False),
    )

    length_button = ft.FilledButton(
        content=ft.Row(
            tight=True,
            controls=[
                ft.Icon(ft.Icons.STRAIGHTEN, color="white"),
                ft.Text(f"ДЛИНА: {selected_length['value']:g}", color="white",
                        weight=ft.FontWeight.BOLD),
            ],
        ),
        style=ft.ButtonStyle(bgcolor="#8C918F", color="white"),
        on_click=open_length_picker,
    )

    table_actions = ft.Container(
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
    )

    volume_row = ft.Container(
        padding=ft.Padding.symmetric(horizontal=12, vertical=7),
        content=ft.Row(
            controls=[
                ft.IconButton(
                    ft.Icons.TUNE, icon_color="#85898C", icon_size=25,
                    tooltip="Настройки расчёта",
                    on_click=summary.open_settings,
                ),
                total_volume,
                ft.Container(expand=True),
                total_count,
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )

    bottom_host = ft.Container(content=table_actions)
    content_host.content = table_view
    page.add(ft.Column(
        spacing=0,
        expand=True,
        controls=[
            calc_tab_bar(GREEN, [table_tab, summary_tab]),
            volume_row,
            ft.Container(
                content=content_host,
                expand=True,
                padding=ft.Padding.symmetric(horizontal=8),
            ),
            summary.totals,
            bottom_host,
        ],
    ))
    refresh_records()
    if active_tab["value"] == "summary":
        choose_tab("summary")
