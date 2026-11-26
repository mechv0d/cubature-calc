from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

import flet as ft

from app.calculators.gost_2708 import calculate_gost_item, load_gost_table
from app.cylindering import show_cylindering
from app.pdf_export import create_party_pdf
from app.screen_utils import (
    clear_screen_state,
    allow_screen_sleep,
    keep_screen_awake,
    load_screen_state,
    save_screen_state,
    setup_haptic,
    vibrate,
)
from app.storage import (
    delete_party, init_db, list_calculations, list_parties, save_party,
    update_party,
)

GREEN = "#176B4A"
ORANGE = "#E89A4E"
BG = "#F7F8F7"
PANEL = "#E8E9EA"
TEXT = "#62666A"
DIAMETERS = list(range(4, 101))
UNIT_NAMES = {"MM": "мм", "CM": "см", "M": "м"}
ROUNDING_OPTIONS = ("0.0", "0.00", "0.000", "0.0000", "0.00000", "0.000000")
GOST_TABLE = load_gost_table()


def diameter_grid_columns(page):
    """Return 2 columns on phones and never more than 4 columns."""
    width = getattr(page, "width", 0) or 0
    if width >= 1000:
        return 4
    if width >= 700:
        return 3
    return 2


def main(page: ft.Page):
    init_db()
    page.title = "Кубатура Экспресс"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.fonts = {
        "Google Sans": "Google_Sans/static/GoogleSans-Regular.ttf",
    }
    page.theme = ft.Theme(font_family="Google Sans")
    page.dark_theme = ft.Theme(font_family="Google Sans")
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

    def bottom_navigation(selected_index):
        """Навигация разделов, отображаемая только на основных экранах."""
        return ft.NavigationBar(
            selected_index=selected_index,
            on_change=lambda e: (
                show_home() if e.control.selected_index == 0
                else show_parties() if e.control.selected_index == 1
                else show_reference()
            ),
            destinations=[
                ft.NavigationBarDestination(
                    icon=ft.Icons.CALCULATE_OUTLINED,
                    selected_icon=ft.Icons.CALCULATE,
                    label="Расчёт",
                ),
                ft.NavigationBarDestination(
                    icon=ft.Icons.INVENTORY_2_OUTLINED,
                    selected_icon=ft.Icons.INVENTORY_2,
                    label="Партии",
                ),
                ft.NavigationBarDestination(
                    icon=ft.Icons.MENU_BOOK_OUTLINED,
                    selected_icon=ft.Icons.MENU_BOOK,
                    label="Справочник",
                ),
            ],
        )

    def party_date():
        return datetime.now().strftime("%-d.%m") if __import__("os").name != "nt" else datetime.now().strftime("%#d.%m")

    def create_party(party_type, default_name, payload):
        name = ft.TextField(label="Название", value=default_name)
        description = ft.TextField(label="Описание", multiline=True, max_length=500)
        counterparty_name = ft.TextField(label="Контрагент")
        counterparty_phone = ft.TextField(label="Телефон", keyboard_type=ft.KeyboardType.PHONE)
        counterparty_email = ft.TextField(label="Email", keyboard_type=ft.KeyboardType.EMAIL)
        counterparty_info = ft.TextField(label="Дополнительная информация")

        def save(_):
            if not name.value.strip():
                name.error_text = "Укажите название"
                page.update()
                return
            party_id = save_party(
                party_type, name.value.strip(), description.value or "",
                {
                    "name": counterparty_name.value or "",
                    "phone": counterparty_phone.value or "",
                    "email": counterparty_email.value or "",
                    "info": counterparty_info.value or "",
                }, payload,
            )
            draft_screen = {
                "ГОСТ": "gost",
                "Пиломатериал": "lumber",
                "Оцилиндровка": "cylindering",
            }.get(party_type)
            if draft_screen:
                clear_screen_state(draft_screen)
            page.pop_dialog()
            saved_party = next(
                party for party in list_parties() if party["id"] == party_id
            )
            show_party_detail(saved_party)

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.INVENTORY_2_OUTLINED, color=GREEN),
                    ft.Text("Новая партия", weight=ft.FontWeight.BOLD),
                ],
            ),
            content=ft.Column(
                tight=True, spacing=10, scroll=ft.ScrollMode.AUTO,
                controls=[
                    ft.Text("Основные данные", color=GREEN,
                            weight=ft.FontWeight.BOLD),
                    name, description,
                    ft.Text("Контрагент", color=GREEN,
                            weight=ft.FontWeight.BOLD),
                    counterparty_name, counterparty_phone,
                    counterparty_email, counterparty_info,
                ],
            ),
            actions=[
                ft.TextButton("Отмена", on_click=lambda _: page.pop_dialog()),
                ft.FilledButton(
                    "Сохранить", on_click=save,
                    style=ft.ButtonStyle(bgcolor=GREEN, color="white"),
                ),
            ],
        )
        page.show_dialog(dialog)

    def show_home():
        allow_screen_sleep(page)
        page.controls.clear()
        page.navigation_bar = bottom_navigation(0)
        page.appbar = ft.AppBar(
            title=ft.Text("Кубатура Экспресс", weight=ft.FontWeight.W_600),
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
                                "Автономный режим, данные хранятся на устройстве",
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
                            lambda _: show_cylindering(page, show_home, create_party),
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

    def show_parties():
        allow_screen_sleep(page)
        page.controls.clear()
        page.navigation_bar = bottom_navigation(1)
        page.appbar = ft.AppBar(
            title=ft.Text("Партии", weight=ft.FontWeight.W_600),
            bgcolor=GREEN,
            color="white",
            center_title=True,
        )
        cards = ft.Column(spacing=10, scroll=ft.ScrollMode.AUTO, expand=True)

        def refresh():
            cards.controls.clear()
            parties = list_parties()
            if not parties:
                cards.controls.append(ft.Text("Сохранённых партий пока нет.", color=TEXT))
            for party in parties:
                cards.controls.append(ft.Card(
                    elevation=0,
                    bgcolor="#FFFFFF",
                    content=ft.ListTile(
                        leading=ft.Image(
                            src=(
                                "pilomaterial.png"
                                if party["type"] == "Пиломатериал"
                                else "cylinder.png"
                                if party["type"] == "Оцилиндровка"
                                else "krugl.png"
                            ),
                            width=58, height=58,
                            # Flet 0.86 accepts the fit mode as a string;
                            # ImageFit enum is not available in this version.
                            fit="contain",
                        ),
                        title=ft.Text(party["name"], weight=ft.FontWeight.W_600),
                        subtitle=ft.Text(
                            f"{format_party_datetime(party['updated_at'])}"
                            f"{"\n" + party['description'] or ''}"
                        ),
                        trailing=ft.IconButton(
                            ft.Icons.DELETE_OUTLINE,
                            tooltip="Удалить партию",
                            on_click=lambda e, i=party["id"], n=party["name"]: confirm_delete_party(i, n),
                        ),
                        on_click=lambda e, p=party: show_party_detail(p),
                    ),
                ))
            page.update()

        page.add(ft.Container(padding=18, expand=True, content=cards))
        refresh()
        page.update()

    def confirm_delete_party(party_id, party_name, after_delete=None):
        def delete(_):
            page.pop_dialog()
            delete_party(party_id)
            if after_delete:
                after_delete()
            else:
                show_parties()

        page.show_dialog(ft.AlertDialog(
            modal=True,
            title=ft.Text("Удалить партию?"),
            content=ft.Text(
                f'Партия «{party_name}» будет удалена без возможности восстановления.'
            ),
            actions=[
                ft.TextButton("Отмена", on_click=lambda _: page.pop_dialog()),
                ft.TextButton("Удалить", on_click=delete),
            ],
        ))

    def party_totals(party):
        total = Decimal(0)
        count = 0
        for item in party.get("payload", []):
            try:
                total += Decimal(str(item.get("volume_m3", item.get("volume", 0))))
                count += int(item.get("quantity", 0))
            except (TypeError, ValueError, InvalidOperation):
                continue
        return total, count

    def show_party_detail(party):
        """Экран конкретной партии; нижняя навигация здесь намеренно скрыта."""
        page.controls.clear()
        page.navigation_bar = None
        total, count = party_totals(party)
        counterparty = party.get("counterparty") or {}
        table_rows = []
        for item in party.get("payload", []):
            if party["type"] == "Пиломатериал":
                title = f"{item.get('thickness_cm', 0):g}×{item.get('width_cm', 0):g}"
                position = f"Пиломатериал {title}"
                length = f"{item.get('length_m', item.get('length', 0)):g}"
            else:
                title = f"{item.get('diameter_cm', item.get('diameter', 0))} см"
                position = title
                length = f"{item.get('length_m', item.get('length', 0)):g}"
            volume = item.get('volume_m3', item.get('volume', 0))
            quantity = item.get('quantity', 0)
            table_rows.append((position, length, quantity, volume))

        def table_cell(value, width=None, expand=False, **kwargs):
            return ft.Container(
                content=ft.Text(str(value), **kwargs), width=width,
                expand=expand, padding=ft.Padding.symmetric(horizontal=10, vertical=12),
            )

        header = ft.Container(
            bgcolor="#F4F0E1",
            content=ft.Row(expand=True, controls=[
                table_cell("Позиция", expand=True),
                table_cell("Длина, м", width=80),
                table_cell("Шт", width=44),
                table_cell("Объём, м³", width=92),
            ]),
        )
        data_rows = [ft.Container(
            bgcolor="#FFFFFF",
            border=ft.Border(bottom=ft.BorderSide(1, "#D5D9D8")),
            content=ft.Row(expand=True, controls=[
                table_cell(position, expand=True, weight=ft.FontWeight.W_600),
                table_cell(length, width=74),
                table_cell(quantity, width=44),
                table_cell(f"{volume} м³", width=92, color=ORANGE,
                           weight=ft.FontWeight.BOLD),
            ]),
        ) for position, length, quantity, volume in table_rows]
        composition_table = ft.Container(
            bgcolor="#FFFFFF", border=ft.Border.all(1, "#E4E8E4"),
            border_radius=14, clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            content=ft.Column(controls=[
                header,
                *data_rows,
                ft.Container(
                    bgcolor="#FFF3CC", padding=ft.Padding.symmetric(vertical=12, horizontal=10),
                    content=ft.Row(expand=True, controls=[
                        ft.Text("Итого", weight=ft.FontWeight.BOLD, expand=True),
                        ft.Container(width=44, content=ft.Text(str(count), weight=ft.FontWeight.BOLD)),
                        ft.Text(f"{total:.4f} м³", width=92, color=ORANGE,
                                weight=ft.FontWeight.BOLD),
                    ]),
                ),
            ]),
        )

        def edit_party(_):
            open_party_editor(party)

        def delete_current(_):
            confirm_delete_party(party["id"], party["name"])

        def show_counterparty(_):
            if not any(counterparty.values()):
                content = ft.Text("Для этой партии контрагент не указан.")
            else:
                content = ft.Column(tight=True, spacing=8, controls=[
                    ft.Text(counterparty.get("name") or "Без имени",
                            size=20, weight=ft.FontWeight.BOLD),
                    ft.Text(f"Телефон: {counterparty.get('phone') or 'не указан'}"),
                    ft.Text(f"Email: {counterparty.get('email') or 'не указан'}"),
                    ft.Text(f"Дополнительная информация: {counterparty.get('info') or 'не указана'}"),
                ])

            def edit(_):
                page.pop_dialog()
                open_party_editor(party)

            page.show_dialog(ft.AlertDialog(
                modal=True,
                title=ft.Text("Контрагент"),
                content=content,
                actions=[
                    ft.TextButton("Закрыть", on_click=lambda _: page.pop_dialog()),
                    ft.FilledButton("Изменить", on_click=edit,
                                    style=ft.ButtonStyle(bgcolor=GREEN, color="white")),
                ],
            ))

        def export_pdf(_):
            try:
                pdf_path = create_party_pdf(party)
            except RuntimeError as exc:
                page.show_dialog(ft.SnackBar(content=ft.Text(str(exc))))
                return

            def open_pdf(_):
                page.pop_dialog()
                page.launch_url(pdf_path.as_uri())

            def share_pdf(_):
                page.pop_dialog()
                page.show_dialog(ft.SnackBar(
                    content=ft.Text(f"Файл сохранён: {pdf_path.name}. "
                                    "Его можно отправить из папки приложения."),
                ))

            page.show_dialog(ft.AlertDialog(
                modal=True,
                title=ft.Text("Точковка сохранена"),
                content=ft.Text(f"Файл сохранён на устройстве:\n{pdf_path}"),
                actions=[
                    ft.TextButton("Закрыть", on_click=lambda _: page.pop_dialog()),
                    ft.TextButton("Поделиться", on_click=share_pdf),
                    ft.FilledButton("Открыть", on_click=open_pdf,
                                    style=ft.ButtonStyle(bgcolor=GREEN, color="white")),
                ],
            ))

        page.appbar = ft.AppBar(
            leading=ft.IconButton(ft.Icons.ARROW_BACK, on_click=lambda _: show_parties()),
            title=ft.Text(party["name"], size=18), bgcolor=GREEN, color="white",
            actions=[
                ft.IconButton(ft.Icons.EDIT_OUTLINED, on_click=edit_party),
                ft.IconButton(ft.Icons.DELETE_OUTLINE, tooltip="Удалить партию",
                              on_click=delete_current),
            ],
        )
        page.add(ft.Container(
            bgcolor="#FFFFFF", expand=True, padding=ft.Padding.all(16),
            content=ft.Column(expand=True, scroll=ft.ScrollMode.AUTO, spacing=12, controls=[
                ft.Text(party["name"], size=24, weight=ft.FontWeight.BOLD),
                ft.Text(f"Изменено: {format_party_datetime(party['updated_at'])}", color=TEXT),
                 ft.TextButton(
                     "Контрагент: " + (counterparty.get("name") or "не указан"),
                     icon=ft.Icons.PERSON_OUTLINE,
                     on_click=show_counterparty,
                     style=ft.ButtonStyle(color=GREEN),
                 ),
                 ft.Container(bgcolor="#FFFFFF", padding=16, border_radius=14,
                              border=ft.Border.all(2, "#E3B64F"),
                              content=ft.Row(controls=[
                                 ft.Column(spacing=0, controls=[
                                     ft.Text("ОБЪЁМ ПАРТИИ", color="#80651F",
                                             weight=ft.FontWeight.BOLD),
                                     ft.Text(f"{total:.4f} м³", size=30,
                                             color=ORANGE, weight=ft.FontWeight.BOLD),
                                 ], expand=True),
                                 ft.Text(f"{count} шт.", size=20, color=TEXT),
                             ])),
                  ft.Row(expand=True, spacing=8, controls=[
                      ft.FilledButton("Точковка PDF", icon=ft.Icons.PICTURE_AS_PDF,
                                      expand=True, height=64, on_click=export_pdf,
                                      style=ft.ButtonStyle(
                                          bgcolor="#FFF4BE", color="#171A18",
                                          padding=ft.Padding.symmetric(horizontal=4, vertical=4),
                                          shape=ft.RoundedRectangleBorder(radius=12),
                                      )),
                      ft.FilledButton("Удалить", icon=ft.Icons.DELETE_OUTLINE,
                                      expand=True, height=64,
                                      on_click=delete_current,
                                      style=ft.ButtonStyle(
                                          bgcolor="#F8C8C5", color="#171A18",
                                          padding=ft.Padding.symmetric(horizontal=4, vertical=4),
                                          shape=ft.RoundedRectangleBorder(radius=12),
                                      )),
                      ft.FilledButton("Изменить расчеты", icon=ft.Icons.EDIT,
                                      expand=True, height=64,
                                      on_click=lambda _: page.show_dialog(ft.SnackBar(
                                          content=ft.Text("Добавление позиций будет доступно в следующем обновлении."))),
                                      style=ft.ButtonStyle(
                                          bgcolor="#C7DDF4", color="#171A18",
                                          padding=ft.Padding.symmetric(horizontal=4, vertical=4),
                                          shape=ft.RoundedRectangleBorder(radius=12),
                                      )),
                  ]),
                 ft.Text(party.get("description") or "Без описания", color=TEXT),
                 ft.Text("Состав партии", size=19, weight=ft.FontWeight.BOLD),
                 composition_table,
            ]),
        ))
        page.update()

    def open_party_editor(party):
        name = ft.TextField(label="Название", value=party["name"])
        description = ft.TextField(label="Описание", value=party["description"],
                                   multiline=True, max_length=500)
        cp = party.get("counterparty") or {}
        cp_name = ft.TextField(label="Контрагент", value=cp.get("name", ""))
        cp_phone = ft.TextField(label="Телефон", value=cp.get("phone", ""))
        cp_email = ft.TextField(label="Email", value=cp.get("email", ""))
        cp_info = ft.TextField(label="Дополнительная информация", value=cp.get("info", ""))

        def update(_):
            update_party(
                party["id"], name.value, description.value or "", {
                    "name": cp_name.value or "", "phone": cp_phone.value or "",
                    "email": cp_email.value or "", "info": cp_info.value or "",
                }, party["payload"],
            )
            page.pop_dialog()
            refreshed = next(p for p in list_parties() if p["id"] == party["id"])
            show_party_detail(refreshed)

        page.show_dialog(ft.AlertDialog(
            modal=True, title=ft.Text("Изменить партию"),
            content=ft.Column(tight=True, scroll=ft.ScrollMode.AUTO,
                              controls=[name, description, cp_name, cp_phone, cp_email, cp_info]),
            actions=[ft.TextButton("Отмена", on_click=lambda _: page.pop_dialog()),
                     ft.FilledButton("Сохранить", on_click=update,
                                     style=ft.ButtonStyle(bgcolor=GREEN, color="white"))],
        ))

    def format_party_datetime(value):
        try:
            months = ("января", "февраля", "марта", "апреля", "мая", "июня",
                      "июля", "августа", "сентября", "октября", "ноября", "декабря")
            value = datetime.fromisoformat(value)
            return f"{value.day} {months[value.month - 1]} {value.year}, {value:%H:%M}"
        except (TypeError, ValueError):
            return value

    def show_reference():
        allow_screen_sleep(page)
        page.controls.clear()
        page.navigation_bar = bottom_navigation(2)
        page.appbar = ft.AppBar(
            title=ft.Text("Справочник"),
            bgcolor=GREEN,
            color="white",
        )
        page.add(
            ft.Container(
                padding=24,
                content=ft.Text(
                    "Справочная информация о приложении будет добавлена здесь.",
                    size=16,
                    color=TEXT,
                ),
            )
        )
        page.update()

    def show_placeholder(title):
        page.controls.clear()
        page.navigation_bar = None
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
        keep_screen_awake(page)
        setup_haptic(page)
        page.controls.clear()
        page.navigation_bar = None
        active_tab["value"] = "table"
        page.appbar = ft.AppBar(
            leading=ft.IconButton(ft.Icons.ARROW_BACK, on_click=lambda _: show_home()),
            title=ft.Text("Расчёт · ГОСТ 2708-75", size=18),
            bgcolor=GREEN,
            color="white",
            center_title=True,
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
                ),
            ],
        )

        total_volume = ft.Text("0.0000 м³", size=25, color=ORANGE,
                               weight=ft.FontWeight.BOLD)
        total_count = ft.Text("0 шт.", size=17, color=TEXT)
        items_column = ft.Column(spacing=7, scroll=ft.ScrollMode.AUTO, expand=True)
        table_view = ft.Row(spacing=8, expand=True,
                            vertical_alignment=ft.CrossAxisAlignment.STRETCH)
        summary_view = ft.Column(spacing=12, expand=True)
        content_host = ft.Container(expand=True, content=table_view)

        def format_gost_volume(value):
            quantum = Decimal("0.0001")
            return f"{value.quantize(quantum, rounding=ROUND_HALF_UP):.4f}"

        def format_length(value):
            text = f"{value:g}"
            return f"{text}.0" if "." not in text else text

        # Restore the draft so the calculation survives an app/phone restart.
        draft = load_screen_state("gost")
        current_items.clear()
        for saved_item in draft.get("items", []):
            try:
                volume = Decimal(str(saved_item["volume"]))
            except (KeyError, InvalidOperation, TypeError, ValueError):
                continue
            current_items.append({
                "diameter": int(saved_item["diameter"]),
                "length": float(saved_item["length"]),
                "quantity": max(1, int(saved_item["quantity"])),
                "volume": volume,
                "display_volume": format_gost_volume(volume),
            })
        try:
            selected_length["value"] = float(draft.get("length", 6.0))
        except (TypeError, ValueError):
            selected_length["value"] = 6.0
        if draft.get("tab") == "summary":
            active_tab["value"] = "summary"

        def save_state():
            save_screen_state("gost", {
                "items": current_items,
                "length": selected_length["value"],
                "tab": active_tab["value"],
            })

        def confirm_clear_records():
            def clear(_):
                current_items.clear()
                save_state()
                page.pop_dialog()
                refresh_items()

            page.show_dialog(ft.AlertDialog(
                modal=True,
                title=ft.Text("Очистить записи?"),
                content=ft.Text("Все добавленные брёвна будут удалены."),
                actions=[
                    ft.TextButton("Отмена", on_click=lambda _: page.pop_dialog()),
                    ft.TextButton("Очистить", on_click=clear),
                ],
            ))

        def refresh_summary():
            summary_view.controls.clear()
            total = sum(
                (item["volume"] for item in current_items), Decimal(0)
            )
            count = sum(item["quantity"] for item in current_items)
            summary_view.controls.extend([
                ft.Text("Итоги расчёта", size=22, weight=ft.FontWeight.BOLD),
                ft.Text("Чтобы сохранить расчёт в партию, нажмите соответствующую кнопку внизу экрана", size=14),
                ft.Row(controls=[
                    ft.Text("Количество брёвен", size=16),
                    ft.Container(expand=True),
                    ft.Text(f"{count} шт.", size=17,
                            weight=ft.FontWeight.BOLD),
                ]),
                ft.Row(controls=[
                    ft.Text("Общая кубатура", size=16),
                    ft.Container(expand=True),
                    ft.Text(f"{format_gost_volume(total)} м³", size=17,
                            color=ORANGE, weight=ft.FontWeight.BOLD),
                ]),
            ])
            for item in current_items:
                summary_view.controls.append(ft.Row(controls=[
                    ft.Text(
                        f"Ø{item['diameter']} · "
                        f"{format_length(item['length'])} м",
                        size=14, color=TEXT,
                    ),
                    ft.Container(expand=True),
                    ft.Text(f"{item['quantity']} шт.", size=14, color=TEXT),
                    ft.Text(f"{item['display_volume']} м³", size=14,
                            color=ORANGE, weight=ft.FontWeight.BOLD),
                ]))

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
                                        ft.Text(
                                            f"{format_length(item['length'])} м",
                                            size=13, color=TEXT, no_wrap=True,
                                        ),
                                        ft.Text("·", size=13, color=TEXT),
                                        ft.Text(f"{item['quantity']} шт.", size=13,
                                                color=TEXT, no_wrap=True),
                                    ],
                                ),
                                ft.Column(
                                    spacing=0,
                                    horizontal_alignment=ft.CrossAxisAlignment.END,
                                    controls=[
                                        ft.Text(f"{item['display_volume']} м³",
                                                size=16, color=ORANGE,
                                                weight=ft.FontWeight.BOLD,
                                                no_wrap=True),
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
            total = sum(
                (item["volume"] for item in current_items), Decimal(0)
            )
            total_volume.value = f"{format_gost_volume(total)} м³"
            if active_tab["value"] == "summary":
                refresh_summary()
            save_state()
            page.update()

        def remove_item(index):
            if 0 <= index < len(current_items):
                current_items.pop(index)
                refresh_items()

        def show_missing_table_value(diameter, length):
            def close_dialog(_):
                page.pop_dialog()
                page.update()

            page.show_dialog(ft.AlertDialog(
                modal=True,
                title=ft.Text("Нет значения в таблице"),
                content=ft.Text(
                    f"Для диаметра {diameter} см и длины {length:g} м "
                    "нет значения в таблице ГОСТ 2708-75. "
                    "Выберите другую длину или диаметр."
                ),
                actions=[
                    ft.FilledButton("Закрыть", on_click=close_dialog),
                ],
            ))

        def add_diameter(diameter):
            length = Decimal(str(selected_length["value"]))
            try:
                volume = calculate_gost_item(
                    diameter, length, 1, GOST_TABLE
                )
            except ValueError:
                show_missing_table_value(diameter, selected_length["value"])
                return
            current_items.append({
                "diameter": diameter,
                "length": selected_length["value"],
                "quantity": 1,
                "volume": volume,
                "display_volume": format_gost_volume(volume),
            })
            refresh_items()
            vibrate(page)

        def save_gost_party(_):
            if not current_items:
                page.show_dialog(ft.SnackBar(content=ft.Text("Сначала добавьте хотя бы одно бревно.")))
                return
            create_party("ГОСТ", "Кругляк " + party_date(), [
                {**item, "volume": str(item["volume"])} for item in current_items
            ])

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
            save_state()
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
                save_state()
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
            expand=True, runs_count=diameter_grid_columns(page), spacing=5, run_spacing=5,
            child_aspect_ratio=1.08,
            controls=[
                ft.FilledButton(
                    content=ft.Text(str(d), size=22, no_wrap=True,
                                    text_align=ft.TextAlign.CENTER),
                    height=72,
                    style=ft.ButtonStyle(
                        bgcolor="#E5E6E7", color=TEXT,
                        padding=ft.Padding.symmetric(horizontal=2, vertical=4),
                        shape=ft.RoundedRectangleBorder(radius=0), elevation=0,
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
            style=ft.ButtonStyle(
                color="white", bgcolor=GREEN,
                shape=ft.RoundedRectangleBorder(radius=0),
            ),
        )
        summary_tab = ft.TextButton(
            "Итоги", expand=True, on_click=lambda _: choose_tab("summary"),
            style=ft.ButtonStyle(
                color="#B8D4C8", bgcolor=GREEN,
                shape=ft.RoundedRectangleBorder(radius=0),
            ),
        )
        length_button = ft.FilledButton(
            content=ft.Row(tight=True, controls=[
                ft.Icon(ft.Icons.STRAIGHTEN, color="white"),
                ft.Text(f"ДЛИНА: {selected_length['value']:g}", color="white",
                        weight=ft.FontWeight.BOLD),
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
                            expand=True, on_click=save_gost_party,
                            style=ft.ButtonStyle(bgcolor=GREEN, color="white"),
                        ),
                        length_button,
                    ], spacing=7),
                ),
            ],
        ))
        refresh_items()
        if active_tab["value"] == "summary":
            choose_tab("summary")
        page.update()

    def lumber_volume(item):
        return (
            Decimal(str(item["thickness_cm"])) / Decimal(100)
            * Decimal(str(item["width_cm"])) / Decimal(100)
            * Decimal(str(item["length_m"]))
            * int(item["quantity"])
        )

    def show_lumber_calculator():
        keep_screen_awake(page)
        setup_haptic(page)
        page.controls.clear()
        page.navigation_bar = None
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

        # Restore the draft saved on the previous run (app/phone restart).
        draft = load_screen_state("lumber")
        lumber_items[:] = draft.get("items", [])
        try:
            saved_digits = int(draft.get("rounding", 4))
        except (TypeError, ValueError):
            saved_digits = 4
        rounding_digits = {"value": min(max(saved_digits, 1), 6)}

        def save_state():
            save_screen_state("lumber", {
                "items": lumber_items,
                "rounding": rounding_digits["value"],
            })

        def fmt(value, places=None):
            if places is None:
                places = rounding_digits["value"]
            return f"{value:.{places}f}"

        def rounded_volume(item):
            quantum = Decimal(1).scaleb(-rounding_digits["value"])
            return lumber_volume(item).quantize(
                quantum, rounding=ROUND_HALF_UP
            )

        def change_rounding(e):
            value = e.control.value
            if not value:
                return
            rounding_digits["value"] = len(value.split(".", 1)[1])
            refresh_records()

        rounding_selector = ft.Dropdown(
            label="Округление",
            value="0." + "0" * rounding_digits["value"],
            width=140,
            dense=True,
            text_size=15,
            options=[ft.dropdown.Option(option) for option in ROUNDING_OPTIONS],
            on_select=change_rounding,
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

        def save_lumber_party(_):
            if not lumber_items:
                page.show_dialog(ft.SnackBar(content=ft.Text("Сначала добавьте хотя бы одну позицию.")))
                return
            create_party("Пиломатериал", "Пиломатериал " + party_date(), [
                {**item, "volume_m3": str(rounded_volume(item))}
                for item in lumber_items
            ])

        def confirm_clear_records():
            def clear(_):
                lumber_items.clear()
                save_state()
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
            save_state()
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
                if index is None:
                    vibrate(page)

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
                    content=ft.Row(
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=10,
                        controls=[
                            ft.Column(
                                spacing=0,
                                expand=True,
                                controls=[summary_volume, summary_details],
                            ),
                            rounding_selector,
                        ],
                    ),
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
                    content=ft.Row(expand=True, controls=[
                        ft.FilledButton(
                            content=ft.Row(tight=True, controls=[
                                ft.Icon(ft.Icons.SAVE, color="white"),
                                ft.Text("Сохранить", color="white", weight=ft.FontWeight.BOLD),
                            ]),
                            expand=True, height=56, on_click=save_lumber_party,
                            style=ft.ButtonStyle(bgcolor=GREEN, color="white"),
                        ),
                        ft.FilledButton(
                            content=ft.Row(tight=True, controls=[
                                ft.Icon(ft.Icons.ADD, color="white"),
                                ft.Text("Добавить", color="white", weight=ft.FontWeight.BOLD),
                            ]),
                            expand=True, height=56, on_click=add_lumber,
                            style=ft.ButtonStyle(bgcolor="#E77C3B", color="white"),
                        ),
                    ]),
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
    ft.app(target=main, assets_dir="app/assets")
