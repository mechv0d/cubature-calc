import os
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

import flet as ft

from app.calculators.gost_2708 import calculate_gost_item, load_gost_table
from app.content.guide import (
    DISCLAIMER_TEXT,
    DISCLAIMER_TITLE,
    Article,
    article_by_slug,
    load_article_body,
    load_articles,
    resolve_asset,
)
from app.content.markdown import parse_blocks, parse_inline
from app.cylindering import cylinder_volume, show_cylindering
from app.excel_export import build_calculation_xlsx
from app.navigation import BACK_BLOCKED, Navigator
from app.pdf_export import create_party_pdf, create_party_pdf_bytes
from app.screen_utils import (
    allow_screen_sleep,
    clear_screen_state,
    keep_screen_awake,
    load_screen_state,
    save_screen_state,
    setup_haptic,
    vibrate,
)
from app.storage import (
    DATA_DIR,
    delete_counterparty,
    delete_party,
    find_counterparty_by_name,
    init_db,
    list_counterparties,
    list_parties,
    save_counterparty,
    save_party,
    update_counterparty,
    update_party,
)
from app.summary import (
    TAB_BAR_HEIGHT,
    CalculationSummary,
    ask_quantity,
    calc_tab_bar,
    calc_tab_style,
    default_settings,
    format_length,
    load_settings,
    price_for_diameter,
)

GREEN = "#176B4A"
ORANGE = "#E89A4E"
BG = "#F7F8F7"
PANEL = "#E8E9EA"
TEXT = "#62666A"
GUIDE_BG = "#FBF6E9"
GUIDE_CARD = "#FFFFFF"
GUIDE_BORDER = "#E8E2D4"
GUIDE_INK = "#1B211C"
GUIDE_MUTED = "#6C736C"
GUIDE_HERO_HEIGHT = 320
DIAMETERS = list(range(3, 121))
UNIT_NAMES = {"MM": "мм", "CM": "см", "M": "м"}
#: Варианты округления для пиломатериалов: (значение, подпись в списке).
#: Значение остаётся строкой вида «0.0000» — из него берётся число знаков.
ROUNDING_OPTIONS = tuple(
    (
        "0." + "0" * digits,
        f"{digits} зн." + (" (рек.)" if digits == 4 else ""),
    )
    for digits in range(1, 7)
)

#: Размер картинки (квадрат, px) в карточке партии на экране «Партии».
#: Увеличьте это число, если иконки должны быть крупнее.
PARTY_ICON_SIZE = 70

GOST_TABLE = load_gost_table()

#: Файл с версией приложения рядом с main.py.
VERSION_FILE = Path(__file__).resolve().parent / "app-version.txt"
DEFAULT_VERSION = "0.1"

#: Каталог статических файлов (передаётся в ``ft.run`` как ``assets_dir``).
#:
#: В собранном приложении (APK/desktop) файлы лежат в каталоге, путь к которому
#: Flet передаёт в переменной окружения ``FLET_ASSETS_DIR``, поэтому путь
#: берём оттуда, а для локального запуска — от ``main.py``.
ASSETS_DIR = Path(
    os.environ.get("FLET_ASSETS_DIR")
    or Path(__file__).resolve().parent / "assets"
)


def asset_url(src):
    """Добавить к локальной картинке версию файла.

    Браузер кеширует картинки по URL, поэтому после замены файла он может
    продолжать показывать старую копию даже после перезапуска сервера.
    Время изменения файла в query-параметре делает URL новым, и браузер
    загружает свежую картинку.
    """
    if not src or src.startswith(("http://", "https://", "data:", "/")):
        return src
    if os.environ.get("FLET_ASSETS_DIR"):
        # В собранном приложении (APK/desktop) Flutter ищет картинку по имени
        # файла в пакете ресурсов. Query-строка делает имя несуществующим,
        # поэтому кеш-бастинг оставляем только для веба.
        return src
    try:
        stamp = int((ASSETS_DIR / src.split("?", 1)[0]).stat().st_mtime)
    except OSError:
        return src
    separator = "&" if "?" in src else "?"
    return f"{src}{separator}v={stamp}"


def app_version() -> str:
    """Версия из ``app-version.txt``; если файла нет — «0.1»."""
    try:
        version = VERSION_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return DEFAULT_VERSION
    return version or DEFAULT_VERSION


def format_lumber_size(item):
    """Position label for a lumber item with dimensions in millimetres."""
    def millimetres(key):
        try:
            value = Decimal(str(item.get(key, 0) or 0)) * 10
        except (InvalidOperation, TypeError, ValueError):
            value = Decimal(0)
        return format(value.normalize(), "f")

    return (
        f"{millimetres('thickness_cm')}×"
        f"{millimetres('width_cm')} мм"
    )


def party_item_cost(item):
    """Cost of one saved position, or ``None`` when its price is unknown.

    A zero or missing price means the position was saved without a price, so
    it is reported as unknown instead of a misleading ``0.00``.
    """
    try:
        volume = Decimal(
            str(item.get("volume_m3", item.get("volume", 0)) or 0)
        )
    except (InvalidOperation, TypeError, ValueError):
        volume = Decimal(0)
    cost = None
    price_value = item.get("price_per_m3")
    if price_value not in (None, ""):
        try:
            price = Decimal(str(price_value))
        except (InvalidOperation, TypeError, ValueError):
            price = None
        if price is not None and price > 0:
            cost = volume * price
    if cost is None and item.get("cost") not in (None, ""):
        try:
            stored = Decimal(str(item["cost"]))
        except (InvalidOperation, TypeError, ValueError):
            stored = None
        if stored is not None and stored > 0:
            cost = stored
    return cost


def party_calculation_data(party):
    """Build the XLSX-ready summary for a saved party of any type."""
    payload = party.get("payload") or []
    rows = []
    total_volume = Decimal(0)
    total_quantity = 0
    total_cost = Decimal(0)
    prices = []
    species = "н/д"
    calc_type = "н/д"
    for item in payload:
        if item.get("species"):
            species = item["species"]
        if item.get("calc_type"):
            calc_type = item["calc_type"]
        try:
            quantity = int(item.get("quantity", 0) or 0)
        except (TypeError, ValueError):
            quantity = 0
        try:
            volume = Decimal(
                str(item.get("volume_m3", item.get("volume", 0)) or 0)
            )
        except (InvalidOperation, TypeError, ValueError):
            volume = Decimal(0)
        price_value = None
        if item.get("price_per_m3") not in (None, ""):
            try:
                price_value = Decimal(str(item["price_per_m3"]))
            except (InvalidOperation, TypeError, ValueError):
                price_value = None
            else:
                prices.append(price_value)
        cost = party_item_cost(item)
        if party.get("type") == "Пиломатериал":
            label = format_lumber_size(item)
        else:
            label = str(item.get("diameter_cm", item.get("diameter", 0)))
        length = item.get("length_m", item.get("length", 0)) or 0
        rows.append({
            "label": label,
            "length": f"{float(length):g}",
            "quantity": quantity,
            "volume": float(volume),
            "cost": float(cost) if cost is not None else None,
            "bold": False,
        })
        total_volume += volume
        total_quantity += quantity
        if cost is not None:
            total_cost += cost

    if prices:
        unique = sorted(set(prices))
        if len(unique) == 1:
            price_text = f"{unique[0]:.1f} RUB."
        else:
            price_text = f"от {unique[0]:.1f} до {unique[-1]:.1f} RUB."
    else:
        price_text = "0.0 RUB."

    try:
        updated = datetime.fromisoformat(party.get("updated_at") or "")
        date_text = updated.strftime("%d.%m.%Y")
    except (TypeError, ValueError):
        date_text = datetime.now().strftime("%d.%m.%Y")

    counterparty = party.get("counterparty") or {}
    return {
        "number": party.get("id", ""),
        "title": party.get("name", "Расчёт"),
        "date": date_text,
        "species": species,
        "calc_type": calc_type,
        "counterparty": counterparty.get("name") or "н/д",
        "counterparty_phone": counterparty.get("phone") or "",
        "counterparty_email": counterparty.get("email") or "",
        "price_text": price_text,
        "rows": rows,
        "total_quantity": total_quantity,
        "total_volume": float(total_volume),
        "total_cost": float(total_cost),
    }


def diameter_grid_columns(page):
    """Return 2 columns on phones and never more than 4 columns."""
    width = getattr(page, "width", 0) or 0
    if width >= 1000:
        return 4
    if width >= 700:
        return 3
    return 2


def guide_spans(text, size, color):
    """Оформить строку Markdown в набор текстовых фрагментов Flet."""
    spans = []
    for span in parse_inline(text):
        spans.append(
            ft.TextSpan(
                span.text,
                style=ft.TextStyle(
                    size=size,
                    color=color,
                    height=1.45,
                    weight=ft.FontWeight.BOLD if span.bold else None,
                    italic=span.italic,
                    font_family="monospace" if span.code else None,
                    bgcolor="#EFE8D8" if span.code else None,
                ),
                url=span.url,
            )
        )
    return spans


def guide_image(src, width, height=None, radius=14):
    """Картинка статьи: ширина задаётся вручную, чтобы не было переполнения."""
    return ft.Image(
        src=asset_url(resolve_asset(src)),
        width=width,
        height=height,
        fit="cover" if height else None,
        border_radius=radius,
        error_content=ft.Container(
            width=width,
            height=height or 160,
            bgcolor="#EDE7D8",
            alignment=ft.Alignment.CENTER,
            content=ft.Icon(ft.Icons.FOREST, size=34, color="#A9B2A4"),
        ),
    )


def guide_table_button(on_click):
    """Кнопка перехода к полной таблице в начале статьи про ГОСТ."""
    return ft.Container(
        bgcolor=GREEN,
        border_radius=14,
        padding=ft.Padding.symmetric(horizontal=16, vertical=14),
        on_click=on_click,
        data="open-gost-table",
        content=ft.Row(
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Icon(ft.Icons.TABLE_CHART, color="#F6F1E2", size=22),
                ft.Text(
                    "Открыть таблицу 1 ГОСТ 2708-75",
                    size=15, weight=ft.FontWeight.W_600,
                    color="#F6F1E2", expand=True,
                ),
                ft.Icon(ft.Icons.CHEVRON_RIGHT, color="#CBDFD2", size=20),
            ],
        ),
    )


def guide_markdown_controls(markdown, width):
    """Отрисовать Markdown статьи контролами Flet.

    Свой рендер вместо ``ft.Markdown`` выбран ради картинок: у них нужно точно
    задать ширину колонки и скругление, иначе широкая картинка вылезает за
    границы экрана на телефоне.
    """
    controls = []
    for block in parse_blocks(markdown):
        if block.kind == "heading":
            size = {1: 27, 2: 23}.get(block.level, 19)
            controls.append(
                ft.Container(
                    padding=ft.Padding.only(top=6 if controls else 0),
                    content=ft.Text(
                        block.text, size=size,
                        weight=ft.FontWeight.BOLD, color=GUIDE_INK,
                        selectable=True,
                    ),
                )
            )
        elif block.kind == "paragraph":
            controls.append(
                ft.Text(
                    spans=guide_spans(block.text, 17, GUIDE_INK),
                    selectable=True,
                )
            )
        elif block.kind in ("bullets", "ordered"):
            items = []
            for index, item in enumerate(block.items, start=1):
                marker = "•" if block.kind == "bullets" else f"{index}."
                items.append(
                    ft.Row(
                        spacing=10,
                        vertical_alignment=ft.CrossAxisAlignment.START,
                        controls=[
                            ft.Container(
                                width=18,
                                padding=ft.Padding.only(top=2),
                                content=ft.Text(
                                    marker, size=17,
                                    color=ORANGE if block.kind == "bullets"
                                    else GREEN,
                                    weight=ft.FontWeight.BOLD,
                                ),
                            ),
                            ft.Text(
                                spans=guide_spans(item, 17, GUIDE_INK),
                                expand=True,
                                selectable=True,
                            ),
                        ],
                    )
                )
            controls.append(ft.Column(spacing=9, controls=items))
        elif block.kind == "image":
            picture = [guide_image(block.src, width)]
            if block.caption:
                picture.append(
                    ft.Text(
                        block.caption, size=13, italic=True,
                        color=GUIDE_MUTED, selectable=True,
                    )
                )
            controls.append(ft.Column(spacing=6, controls=picture))
        elif block.kind == "quote":
            controls.append(
                ft.Container(
                    padding=ft.Padding.only(left=14, right=8, top=4, bottom=4),
                    border=ft.Border(left=ft.BorderSide(3, ORANGE)),
                    content=ft.Text(
                        spans=guide_spans(block.text, 16, "#4B544C"),
                        selectable=True,
                    ),
                )
            )
        elif block.kind == "divider":
            controls.append(ft.Divider(height=20, color=GUIDE_BORDER))
    return controls


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
    file_picker = {"value": None}
    share_service = {"value": None}

    # Системный «Назад» на телефоне: главные экраны выходят по двойному
    # нажатию, вложенные — возвращают на предыдущий экран.
    navigator = Navigator(page)
    navigator.attach()

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
        # ``%-d``/``%#d`` (день без ведущего нуля) поддерживаются не везде:
        # на Android strftime оставлял в названии партии литерал «-d».
        now = datetime.now()
        return f"{now.day}.{now.month:02d}"

    def create_party(
        party_type, default_name, payload,
        preset_counterparty=None, preset_description="",
    ):
        name = ft.TextField(label="Название", value=default_name)
        description = ft.TextField(
            label="Описание", value=preset_description,
            multiline=True, max_length=500,
        )
        counterparty_select = ft.Dropdown(
            label="Контрагент",
            hint_text="Выберите из списка",
            options=[
                ft.DropdownOption(key=str(cp["id"]), text=cp["name"])
                for cp in list_counterparties()
            ],
        )
        counterparty_name = ft.TextField(label="Название контрагента")
        counterparty_phone = ft.TextField(label="Телефон", keyboard_type=ft.KeyboardType.PHONE)
        counterparty_email = ft.TextField(label="Email", keyboard_type=ft.KeyboardType.EMAIL)
        counterparty_info = ft.TextField(label="Дополнительная информация")
        counterparty_status = ft.Text("", color=GREEN, size=12)

        if preset_counterparty:
            counterparty_name.value = preset_counterparty.get("name", "")
            counterparty_phone.value = preset_counterparty.get("phone", "")
            counterparty_email.value = preset_counterparty.get("email", "")
            counterparty_info.value = preset_counterparty.get("info", "")
            preset_id = preset_counterparty.get("id")
            if preset_id is not None and any(
                str(item["id"]) == str(preset_id)
                for item in list_counterparties()
            ):
                counterparty_select.value = str(preset_id)

        def on_counterparty_select(e):
            selected = next(
                (cp for cp in list_counterparties()
                 if str(cp["id"]) == e.control.value),
                None,
            )
            counterparty_status.value = ""
            if selected:
                counterparty_name.value = selected["name"]
                counterparty_phone.value = selected["phone"]
                counterparty_email.value = selected["email"]
                counterparty_info.value = selected["info"]
                counterparty_name.error_text = None
            page.update()

        counterparty_select.on_select = on_counterparty_select

        def save_counterparty_click(_):
            was_existing = find_counterparty_by_name(counterparty_name.value) is not None
            try:
                counterparty_id = save_counterparty(
                    counterparty_name.value, counterparty_phone.value,
                    counterparty_email.value, counterparty_info.value,
                )
            except ValueError as exc:
                counterparty_name.error_text = str(exc)
                counterparty_status.value = ""
                page.update()
                return
            counterparty_name.error_text = None
            counterparty_select.options = [
                ft.DropdownOption(key=str(cp["id"]), text=cp["name"])
                for cp in list_counterparties()
            ]
            counterparty_select.value = str(counterparty_id)
            counterparty_status.value = (
                "Контрагент обновлён" if was_existing else "Контрагент сохранён"
            )
            page.update()

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
            # На телефоне диалог по умолчанию довольно узкий; поля с
            # контрагентом в нём сжимаются в одну колонку. Задаём ширину
            # вручную, но не шире экрана.
            inset_padding=ft.Padding.symmetric(horizontal=12, vertical=24),
            content_padding=ft.Padding.symmetric(horizontal=16, vertical=12),
            title=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.INVENTORY_2_OUTLINED, color=GREEN),
                    ft.Text("Новая партия", weight=ft.FontWeight.BOLD),
                ],
            ),
            content=ft.Container(
                width=min(
                    520,
                    max(240, (getattr(page, "width", 0) or 420) - 56),
                ),
                content=ft.Column(
                    tight=True, spacing=10, scroll=ft.ScrollMode.AUTO,
                    controls=[
                        ft.Text("Основные данные", color=GREEN,
                                weight=ft.FontWeight.BOLD),
                        name, description,
                        ft.Text("Контрагент", color=GREEN,
                                weight=ft.FontWeight.BOLD),
                        counterparty_select,
                        counterparty_name, counterparty_phone,
                        counterparty_email, counterparty_info,
                        ft.OutlinedButton(
                            "Сохранить контрагента",
                            icon=ft.Icons.PERSON_ADD_ALT_1_OUTLINED,
                            on_click=save_counterparty_click,
                        ),
                        counterparty_status,
                    ],
                ),
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
        navigator.reset("/", show_home)
        page.controls.clear()
        page.bgcolor = BG
        page.navigation_bar = bottom_navigation(0)
        page.appbar = ft.AppBar(
            title=ft.Text(
                f"Кубатура Экспресс v{app_version()}",
                weight=ft.FontWeight.W_600,
            ),
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
                            lambda _: show_cylindering(
                                page, show_home, create_party, navigator
                            ),
),
                    ],
                ),
            )
        )
        page.update()

    def show_parties():
        allow_screen_sleep(page)
        navigator.reset("/parties", show_parties)
        page.controls.clear()
        page.bgcolor = BG
        page.navigation_bar = bottom_navigation(1)
        page.appbar = ft.AppBar(
            title=ft.Text("Партии", weight=ft.FontWeight.W_600),
            bgcolor=GREEN,
            color="white",
            center_title=True,
        )
        cards = ft.Column(spacing=10, scroll=ft.ScrollMode.AUTO, expand=True)
        sort_field = {"value": "created_at"}
        sort_descending = {"value": True}

        def counterparty_name(party):
            return ((party.get("counterparty") or {}).get("name") or "").strip()

        def party_subtitle(party):
            controls = [
                ft.Text(format_party_datetime(party.get("updated_at"))),
            ]
            name = counterparty_name(party)
            if name:
                controls.append(ft.Text(name))
            if party.get("description"):
                # Descriptions can be long; show at most three lines.
                controls.append(ft.Text(
                    party["description"],
                    max_lines=3,
                    overflow=ft.TextOverflow.ELLIPSIS,
                ))
            return ft.Column(controls=controls, spacing=0, tight=True)

        def sort_key(party):
            field = sort_field["value"]
            if field == "name":
                return (party.get("name") or "").casefold()
            if field == "counterparty":
                return counterparty_name(party).casefold()
            if field == "updated_at":
                return party.get("updated_at") or ""
            return party.get("created_at") or ""

        def sort_parties(parties):
            # Партии без значения (например, без контрагента) всегда в конце.
            filled = [party for party in parties if sort_key(party)]
            empty = [party for party in parties if not sort_key(party)]
            filled.sort(key=sort_key, reverse=sort_descending["value"])
            return filled + empty

        def sync_order_button():
            order_button.icon = (
                ft.Icons.ARROW_UPWARD
                if sort_descending["value"]
                else ft.Icons.ARROW_DOWNWARD
            )
            order_button.tooltip = (
                "По убыванию" if sort_descending["value"] else "По возрастанию"
            )

        def on_sort_change(e):
            sort_field["value"] = e.control.value
            sort_descending["value"] = e.control.value in ("created_at", "updated_at")
            sync_order_button()
            refresh()

        def toggle_order(_):
            sort_descending["value"] = not sort_descending["value"]
            sync_order_button()
            refresh()

        sort_dropdown = ft.Dropdown(
            label="Сортировка",
            value=sort_field["value"],
            dense=True,
            expand=True,
            options=[
                ft.DropdownOption(key="name", text="По названию"),
                ft.DropdownOption(key="created_at", text="По дате создания"),
                ft.DropdownOption(key="updated_at", text="По дате изменения"),
                ft.DropdownOption(key="counterparty", text="По контрагенту"),
            ],
            on_select=on_sort_change,
        )
        order_button = ft.IconButton(
            icon=ft.Icons.ARROW_UPWARD,
            tooltip="По убыванию",
            on_click=toggle_order,
        )

        def refresh():
            cards.controls.clear()
            parties = sort_parties(list_parties())
            if not parties:
                cards.controls.append(ft.Text("Сохранённых партий пока нет.", color=TEXT))
            for party in parties:
                cards.controls.append(ft.Card(
                    elevation=0,
                    bgcolor="#FFFFFF",
                    # Карточки лежат на светлом фоне, поэтому нужен аутлайн,
                    # иначе белые карточки сливаются с фоном.
                    shape=ft.RoundedRectangleBorder(
                        radius=14,
                        side=ft.BorderSide(1, "#DCE3DF"),
                    ),
                    content=ft.Container(
                        padding=ft.Padding.symmetric(
                            horizontal=12, vertical=10
                        ),
                        on_click=lambda e, p=party: show_party_detail(p),
                        content=ft.Row(
                            spacing=12,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            controls=[
                                ft.Image(
                                    src=asset_url(
                                        "pilomaterial.png"
                                        if party["type"] == "Пиломатериал"
                                        else "cylinder.png"
                                        if party["type"] == "Оцилиндровка"
                                        else "krugl.png"
                                    ),
                                    width=PARTY_ICON_SIZE,
                                    height=PARTY_ICON_SIZE,
                                    fit="contain",
                                ),
                                ft.Column(
                                    spacing=2,
                                    expand=True,
                                    controls=[
                                        ft.Text(
                                            party["name"],
                                            weight=ft.FontWeight.W_600,
                                            size=16,
                                        ),
                                        party_subtitle(party),
                                    ],
                                ),
                                ft.IconButton(
                                    ft.Icons.DELETE_OUTLINE,
                                    tooltip="Удалить партию",
                                    on_click=lambda e, i=party["id"], n=party[
                                        "name"
                                    ]: confirm_delete_party(i, n),
                                ),
                            ],
                        ),
                    ),
                ))
            page.update()

        page.add(ft.Container(
            padding=18, expand=True,
            content=ft.Column(
                expand=True, spacing=12,
                controls=[
                    ft.FilledButton(
                        "Контрагенты",
                        icon=ft.Icons.PEOPLE_OUTLINE,
                        on_click=lambda _: show_counterparties(),
                        style=ft.ButtonStyle(bgcolor=GREEN, color="white"),
                    ),
                    ft.Row(
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[sort_dropdown, order_button],
                    ),
                    cards,
                ],
            ),
        ))
        refresh()
        page.update()

    def show_counterparties():
        """Справочник контрагентов: добавление, изменение и удаление."""
        allow_screen_sleep(page)
        navigator.push("/counterparties", show_counterparties)
        page.controls.clear()
        page.bgcolor = BG
        page.navigation_bar = bottom_navigation(1)
        page.appbar = ft.AppBar(
            leading=ft.IconButton(ft.Icons.ARROW_BACK,
                                  on_click=lambda _: show_parties()),
            title=ft.Text("Контрагенты", weight=ft.FontWeight.W_600),
            bgcolor=GREEN,
            color="white",
            actions=[
                ft.IconButton(
                    ft.Icons.PERSON_ADD_ALT_1_OUTLINED,
                    tooltip="Добавить контрагента",
                    on_click=lambda _: open_counterparty_editor(),
                ),
            ],
        )
        cards = ft.Column(spacing=10, scroll=ft.ScrollMode.AUTO, expand=True)

        def open_counterparty_editor(counterparty=None):
            is_new = counterparty is None
            counterparty = counterparty or {}
            name = ft.TextField(
                label="Название", value=counterparty.get("name", ""),
            )
            phone = ft.TextField(
                label="Телефон", value=counterparty.get("phone", ""),
                keyboard_type=ft.KeyboardType.PHONE,
            )
            email = ft.TextField(
                label="Email", value=counterparty.get("email", ""),
                keyboard_type=ft.KeyboardType.EMAIL,
            )
            info = ft.TextField(
                label="Дополнительная информация",
                value=counterparty.get("info", ""),
            )

            def save(_):
                try:
                    if is_new:
                        save_counterparty(
                            name.value, phone.value, email.value, info.value,
                        )
                    else:
                        update_counterparty(
                            counterparty["id"], name.value,
                            phone.value, email.value, info.value,
                        )
                except ValueError as exc:
                    name.error_text = str(exc)
                    page.update()
                    return
                page.pop_dialog()
                refresh()

            page.show_dialog(ft.AlertDialog(
                modal=True,
                title=ft.Text(
                    "Новый контрагент" if is_new else "Изменить контрагента"
                ),
                content=ft.Column(
                    tight=True, spacing=10, scroll=ft.ScrollMode.AUTO,
                    controls=[name, phone, email, info],
                ),
                actions=[
                    ft.TextButton("Отмена", on_click=lambda _: page.pop_dialog()),
                    ft.FilledButton(
                        "Сохранить", on_click=save,
                        style=ft.ButtonStyle(bgcolor=GREEN, color="white"),
                    ),
                ],
            ))

        def confirm_delete(counterparty):
            def delete(_):
                page.pop_dialog()
                delete_counterparty(counterparty["id"])
                refresh()

            page.show_dialog(ft.AlertDialog(
                modal=True,
                title=ft.Text("Удалить контрагента?"),
                content=ft.Text(
                    f'Контрагент «{counterparty["name"]}» будет удалён из '
                    "справочника. В сохранённых партиях его данные останутся."
                ),
                actions=[
                    ft.TextButton("Отмена", on_click=lambda _: page.pop_dialog()),
                    ft.TextButton("Удалить", on_click=delete),
                ],
            ))

        def refresh():
            cards.controls.clear()
            counterparties = list_counterparties()
            if not counterparties:
                cards.controls.append(
                    ft.Text("Сохранённых контрагентов пока нет.", color=TEXT)
                )
            for counterparty in counterparties:
                contacts = " · ".join(
                    part for part in (
                        counterparty["phone"], counterparty["email"],
                    ) if part
                ) or "Контакты не указаны"
                cards.controls.append(ft.Card(
                    elevation=0,
                    bgcolor="#FFFFFF",
                    content=ft.ListTile(
                        leading=ft.Icon(ft.Icons.PERSON_OUTLINE, color=GREEN),
                        title=ft.Text(
                            counterparty["name"], weight=ft.FontWeight.W_600,
                        ),
                        subtitle=ft.Text(contacts),
                        trailing=ft.Row(
                            tight=True, spacing=0,
                            controls=[
                                ft.IconButton(
                                    ft.Icons.EDIT_OUTLINED,
                                    tooltip="Изменить контрагента",
                                    on_click=lambda e, c=counterparty:
                                    open_counterparty_editor(c),
                                ),
                                ft.IconButton(
                                    ft.Icons.DELETE_OUTLINE,
                                    tooltip="Удалить контрагента",
                                    on_click=lambda e, c=counterparty:
                                    confirm_delete(c),
                                ),
                            ],
                        ),
                    ),
                ))
            page.update()

        page.add(ft.Container(
            padding=18, expand=True,
            content=ft.Column(
                expand=True, spacing=12,
                controls=[
                    ft.FilledButton(
                        "Добавить контрагента",
                        icon=ft.Icons.PERSON_ADD_ALT_1_OUTLINED,
                        on_click=lambda _: open_counterparty_editor(),
                        style=ft.ButtonStyle(bgcolor=GREEN, color="white"),
                    ),
                    cards,
                ],
            ),
        ))
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
        navigator.push(
            f"/party/{party.get('id', '')}",
            lambda: show_party_detail(party),
        )
        page.controls.clear()
        page.navigation_bar = None
        total, count = party_totals(party)
        counterparty = party.get("counterparty") or {}
        volume_digits = 3 if party["type"] == "ГОСТ" else 4
        table_rows = []
        total_cost = Decimal(0)
        has_cost = False
        prices = []
        for item in party.get("payload", []):
            if item.get("price_per_m3") not in (None, ""):
                try:
                    price = Decimal(str(item["price_per_m3"]))
                except (InvalidOperation, TypeError, ValueError):
                    continue
                if price > 0:
                    prices.append(price)
            if party["type"] == "Пиломатериал":
                position = format_lumber_size(item)
                length = f"{item.get('length_m', item.get('length', 0)):g}"
            else:
                title = f"{item.get('diameter_cm', item.get('diameter', 0))} см"
                position = title
                length = f"{item.get('length_m', item.get('length', 0)):g}"
            volume = item.get('volume_m3', item.get('volume', 0))
            try:
                volume = f"{Decimal(str(volume)):.{volume_digits}f}"
            except (InvalidOperation, TypeError, ValueError):
                pass
            quantity = item.get('quantity', 0)
            cost = party_item_cost(item)
            if cost is None:
                cost_text = "—"
            else:
                total_cost += cost
                has_cost = True
                cost_text = f"{cost:.2f}"
            table_rows.append((position, length, quantity, volume, cost_text))

        total_cost_text = f"{total_cost:.2f}" if has_cost else "—"
        unique_prices = sorted(set(prices))
        if not unique_prices:
            price_hint = "н/д"
        elif len(unique_prices) == 1:
            price_hint = f"{unique_prices[0]:.1f} ₽"
        else:
            price_hint = (
                f"{unique_prices[0]:.1f}–{unique_prices[-1]:.1f} ₽"
            )

        def table_cell(value, width=None, expand=False, **kwargs):
            return ft.Container(
                content=ft.Text(str(value), **kwargs), width=width,
                expand=expand, padding=ft.Padding.symmetric(horizontal=4, vertical=12),
            )

        header = ft.Container(
            bgcolor="#F4F0E1",
            content=ft.Row(expand=True, controls=[
                table_cell("Позиция", expand=True, size=12),
                table_cell("Длина, м", width=52, size=12),
                table_cell("Шт", width=28, size=12),
                table_cell("Объём, м³", width=58, size=12),
                table_cell("Сумма, ₽", width=56, size=12),
            ]),
        )
        data_rows = [ft.Container(
            bgcolor="#FFFFFF",
            border=ft.Border(bottom=ft.BorderSide(1, "#D5D9D8")),
            content=ft.Row(expand=True, controls=[
                table_cell(position, expand=True, weight=ft.FontWeight.W_600),
                table_cell(length, width=32),
                table_cell(quantity, width=28),
                table_cell(f"{volume}", width=58, size=12, color=ORANGE,
                           weight=ft.FontWeight.BOLD),
                table_cell(cost_text, width=62, size=12, color="#1B211C",
                           weight=ft.FontWeight.W_600),
            ]),
        ) for position, length, quantity, volume, cost_text in table_rows]
        composition_table = ft.Container(
            bgcolor="#FFFFFF", border=ft.Border.all(1, "#E4E8E4"),
            border_radius=14, clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            content=ft.Column(controls=[
                header,
                *data_rows,
                ft.Container(
                    bgcolor="#FFF3CC",
                    content=ft.Row(expand=True, controls=[
                        table_cell("Итого", expand=True,
                                   weight=ft.FontWeight.BOLD),
                        table_cell("", width=50),
                        table_cell(str(count), width=28,
                                   weight=ft.FontWeight.BOLD),
                        table_cell(
                            f"{total:.{volume_digits}f}", width=58,
                            size=12, color=ORANGE, weight=ft.FontWeight.BOLD,
                        ),
                        table_cell(
                            total_cost_text, width=62,
                            size=12, color="#1B211C", weight=ft.FontWeight.BOLD,
                        ),
                    ]),
                ),
            ]),
        )

        def edit_party(_):
            open_party_editor(party)

        def delete_current(_):
            confirm_delete_party(party["id"], party["name"])

        def confirm_edit_calculations(_):
            def proceed(_):
                page.pop_dialog()
                open_payload_editor(party)

            page.show_dialog(ft.AlertDialog(
                modal=True,
                title=ft.Text("Изменить расчёты?"),
                content=ft.Text(
                    "Откроется редактор позиций партии. Количество и состав "
                    "позиций можно будет изменить."
                ),
                actions=[
                    ft.TextButton("Отмена", on_click=lambda _: page.pop_dialog()),
                    ft.FilledButton(
                        "Изменить", on_click=proceed,
                        style=ft.ButtonStyle(bgcolor=GREEN, color="white"),
                    ),
                ],
            ))

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

        def is_mobile():
            platform = getattr(page, "platform", None)
            check = getattr(platform, "is_mobile", None)
            return bool(check and check())

        def needs_download_dialog():
            """Web/mobile cannot open a server-side ``file://`` path.

            In those modes the PDF bytes must be handed to the client, which
            offers them as a regular browser/app download.
            """
            return bool(getattr(page, "web", False)) or is_mobile()

        def attach_service(service):
            services = getattr(page, "services", None)
            if services is not None and all(
                existing is not service for existing in services
            ):
                services.append(service)
            return service

        async def share_file_bytes(data, file_name, mime_type, title):
            """Open the Android/iOS share sheet with a generated file.

            Saving through ``FilePicker.save_file`` only downloads the file;
            on a phone users expect the system "Поделиться" dialog, from which
            they can send the document to WhatsApp, mail or a drive.
            """
            service = share_service["value"]
            if service is None:
                service = ft.Share()
                share_service["value"] = service
            attach_service(service)
            try:
                await service.share_files(
                    [ft.ShareFile.from_bytes(
                        data, mime_type=mime_type, name=file_name,
                    )],
                    title=title,
                )
            except Exception as exc:  # noqa: BLE001 - surface any platform error
                page.show_dialog(ft.SnackBar(
                    content=ft.Text(f"Не удалось поделиться файлом: {exc}"),
                ))

        async def save_file_bytes(
            data, file_name, extension, dialog_title, success_text,
        ):
            picker = file_picker["value"]
            if picker is None:
                picker = ft.FilePicker()
                file_picker["value"] = picker
            attach_service(picker)
            try:
                await picker.save_file(
                    dialog_title=dialog_title,
                    file_name=file_name,
                    file_type=ft.FilePickerFileType.CUSTOM,
                    allowed_extensions=[extension],
                    src_bytes=data,
                )
            except (OSError, ValueError) as exc:
                page.show_dialog(ft.SnackBar(
                    content=ft.Text(f"Не удалось сохранить файл: {exc}"),
                ))
                return
            page.show_dialog(ft.SnackBar(content=ft.Text(success_text)))

        async def download_excel(_):
            try:
                data = build_calculation_xlsx(party_calculation_data(party))
            except RuntimeError as exc:
                page.show_dialog(ft.SnackBar(content=ft.Text(str(exc))))
                return
            file_name = f"расчет_{party['id']}.xlsx"
            if is_mobile():
                await share_file_bytes(
                    data, file_name,
                    "application/vnd.openxmlformats-officedocument"
                    ".spreadsheetml.sheet",
                    "Расчёт Excel",
                )
                return
            if needs_download_dialog():
                await save_file_bytes(
                    data, file_name, "xlsx", "Сохранить расчёт",
                    "Excel сохранён",
                )
                return
            path = Path(DATA_DIR) / file_name
            try:
                path.write_bytes(data)
            except OSError as exc:
                page.show_dialog(ft.SnackBar(
                    content=ft.Text(f"Не удалось сохранить Excel: {exc}"),
                ))
                return
            page.show_dialog(ft.SnackBar(
                content=ft.Text(f"Excel сохранён: {path}"),
            ))

        async def export_pdf(_):
            if needs_download_dialog():
                # Keep nothing on the server: render in memory and let the
                # client share or save the bytes itself.
                try:
                    pdf_bytes = create_party_pdf_bytes(party)
                except RuntimeError as exc:
                    page.show_dialog(ft.SnackBar(content=ft.Text(str(exc))))
                    return
                file_name = f"точковка_{party['id']}.pdf"
                if is_mobile():
                    await share_file_bytes(
                        pdf_bytes, file_name, "application/pdf", "Точковка",
                    )
                    return
                await save_file_bytes(
                    pdf_bytes, file_name, "pdf", "Сохранить точковку",
                    "PDF сохранён",
                )
                return

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
                ft.IconButton(ft.Icons.EDIT_NOTE, tooltip="Изменить партию",
                              on_click=edit_party),
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
                                 ft.Column(spacing=0, expand=True, controls=[
                                     ft.Text("ОБЪЁМ ПАРТИИ", color="#80651F",
                                             weight=ft.FontWeight.BOLD),
                                     ft.Text(f"{total:.{volume_digits}f} м³", size=22,
                                             color=ORANGE, weight=ft.FontWeight.BOLD),
                                     ft.Text(f"{count} шт.", size=15, color=TEXT),
                                 ]),
                                 ft.Column(
                                     spacing=0, expand=True,
                                     horizontal_alignment=ft.CrossAxisAlignment.END,
                                     controls=[
                                         ft.Text(
                                             "СУММА", color="#80651F",
                                             weight=ft.FontWeight.BOLD,
                                             text_align=ft.TextAlign.RIGHT,
                                         ),
                                         ft.Text(
                                             f"{total_cost_text} ₽" if has_cost
                                             else "—",
                                             size=22,
                                             color="#1B211C",
                                             weight=ft.FontWeight.BOLD,
                                             text_align=ft.TextAlign.RIGHT,
                                         ),
                                         ft.Text(
                                             f"Цена 1 м³: {price_hint}",
                                             size=12, color=TEXT,
                                             text_align=ft.TextAlign.RIGHT,
                                         ),
                                     ],
                                 ),
                             ])),
                  ft.Row(expand=True, spacing=8, controls=[
                      ft.FilledButton("Точковка PDF", icon=ft.Icons.PICTURE_AS_PDF,
                                      expand=True, height=64, on_click=export_pdf,
                                      style=ft.ButtonStyle(
                                          bgcolor="#FFF4BE", color="#171A18",
                                          padding=ft.Padding.symmetric(horizontal=4, vertical=4),
                                          shape=ft.RoundedRectangleBorder(radius=12),
                                      )),
                      ft.FilledButton("Расчёт Excel", icon=ft.Icons.TABLE_VIEW,
                                      expand=True, height=64,
                                      on_click=download_excel,
                                      style=ft.ButtonStyle(
                                          bgcolor="#D9EAD3", color="#171A18",
                                          padding=ft.Padding.symmetric(horizontal=4, vertical=4),
                                          shape=ft.RoundedRectangleBorder(radius=12),
                                      )),
                  ]),
                  ft.Row(expand=True, spacing=8, controls=[
                      ft.OutlinedButton(
                          content=ft.Text("Удалить"),
                          icon=ft.Icons.DELETE_OUTLINE, icon_color="#B3261E",
                          expand=True, height=56,
                          on_click=delete_current,
                          style=ft.ButtonStyle(
                              bgcolor="#FFFFFF",
                              color="#171A18",
                              side=ft.BorderSide(2, "#F8C8C5"),
                              shape=ft.RoundedRectangleBorder(radius=12),
                          ),
                      ),
                      ft.OutlinedButton(
                          content=ft.Text("Изменить расчёты"),
                          icon=ft.Icons.EDIT_NOTE, icon_color="#1B5E9C",
                          expand=True, height=56,
                          on_click=confirm_edit_calculations,
                          style=ft.ButtonStyle(
                              bgcolor="#FFFFFF",
                              color="#171A18",
                              side=ft.BorderSide(2, "#C7DDF4"),
                              shape=ft.RoundedRectangleBorder(radius=12),
                          ),
                      ),
                  ]),
                 ft.Text(party.get("description") or "Без описания", color=TEXT),
                 ft.Text("Состав партии", size=19, weight=ft.FontWeight.BOLD),
                 composition_table,
            ]),
        ))
        page.update()

    def open_payload_editor(party):
        """Edit party positions: quantity, removal and adding new rows."""
        party_type = party["type"]
        items = [dict(item) for item in party.get("payload") or []]
        rows_column = ft.Column(spacing=8)

        def item_label(item):
            if party_type == "Пиломатериал":
                length = float(item.get('length_m', 0) or 0)
                return f"{format_lumber_size(item)} · {length:g} м"
            diameter = item.get("diameter_cm", item.get("diameter", 0))
            length = item.get("length_m", item.get("length", 0)) or 0
            return f"Ø{diameter} · {float(length):g} м"

        def volume_of(item):
            quantity = max(1, int(item.get("quantity", 1) or 1))
            if party_type == "Пиломатериал":
                volume = (
                    Decimal(str(item.get("thickness_cm", 0) or 0)) / 100
                    * Decimal(str(item.get("width_cm", 0) or 0)) / 100
                    * Decimal(str(item.get("length_m", 0) or 0))
                    * quantity
                )
                return volume.quantize(Decimal("0.0001"))
            if party_type == "Оцилиндровка":
                return Decimal(str(cylinder_volume(
                    float(item.get("diameter_cm", 0) or 0),
                    float(item.get("length_m", 0) or 0),
                    quantity,
                ))).quantize(Decimal("0.001"))
            length = Decimal(
                str(item.get("length", item.get("length_m", 0)) or 0)
            )
            try:
                volume = calculate_gost_item(
                    int(item.get("diameter", 0) or 0), length, quantity,
                    GOST_TABLE,
                )
            except (InvalidOperation, TypeError, ValueError):
                volume = Decimal(0)
            return volume.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

        def apply_volume(item):
            item["quantity"] = max(1, int(item.get("quantity", 1) or 1))
            volume = volume_of(item)
            if party_type == "ГОСТ":
                item["volume"] = str(volume)
                item["display_volume"] = f"{volume:.3f}"
                try:
                    price = Decimal(str(item.get("price_per_m3", 0) or 0))
                except (InvalidOperation, TypeError, ValueError):
                    price = Decimal(0)
                item["cost"] = str(volume * price)
            else:
                item["volume_m3"] = str(volume)

        def format_volume(item):
            digits = 4 if party_type == "Пиломатериал" else 3
            value = item.get("volume_m3", item.get("volume", 0))
            try:
                return f"{Decimal(str(value)):.{digits}f} м³"
            except (InvalidOperation, TypeError, ValueError):
                return f"{value} м³"

        def render_rows():
            rows_column.controls.clear()
            if not items:
                rows_column.controls.append(
                    ft.Text("В партии нет позиций.", color=TEXT)
                )
            for index, item in enumerate(items):
                quantity_field = ft.TextField(
                    value=str(item.get("quantity", 1)),
                    width=66, dense=True, text_size=14,
                    keyboard_type=ft.KeyboardType.NUMBER,
                    text_align=ft.TextAlign.CENTER,
                )
                volume_text = ft.Text(
                    format_volume(item), size=13, color=TEXT, no_wrap=True,
                )

                def change_quantity(e, i=index, vol=volume_text):
                    try:
                        quantity = int(str(e.control.value).strip())
                    except (TypeError, ValueError):
                        return
                    if quantity < 1:
                        return
                    items[i]["quantity"] = quantity
                    apply_volume(items[i])
                    vol.value = format_volume(items[i])
                    page.update()

                quantity_field.on_change = change_quantity

                def remove_position(e, i=index):
                    if 0 <= i < len(items):
                        items.pop(i)
                    render_rows()
                    page.update()

                rows_column.controls.append(ft.Container(
                    padding=ft.Padding.symmetric(horizontal=8, vertical=6),
                    border_radius=10, bgcolor="#F5F6F6",
                    content=ft.Row(
                        spacing=6,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Column(
                                spacing=2, expand=True,
                                controls=[
                                    ft.Text(
                                        item_label(item), size=14,
                                        weight=ft.FontWeight.W_600,
                                    ),
                                    volume_text,
                                ],
                            ),
                            quantity_field,
                            ft.IconButton(
                                ft.Icons.DELETE_OUTLINE, icon_size=20,
                                tooltip="Удалить позицию",
                                on_click=remove_position,
                            ),
                        ],
                    ),
                ))

        def number_field(label, value=""):
            return ft.TextField(
                label=label, value=value, width=116, dense=True, text_size=14,
                keyboard_type=ft.KeyboardType.NUMBER,
            )

        if party_type == "Пиломатериал":
            add_fields = {
                "thickness_cm": number_field("Толщина, см"),
                "width_cm": number_field("Ширина, см"),
                "length_m": number_field("Длина, м"),
            }
        elif party_type == "Оцилиндровка":
            add_fields = {
                "diameter_cm": number_field("Диаметр, см"),
                "length_m": number_field("Длина, м"),
            }
        else:
            add_fields = {
                "diameter": number_field("Диаметр, см"),
                "length": number_field("Длина, м"),
            }
        add_quantity = ft.TextField(
            label="Кол-во, шт", value="1", width=110, dense=True,
            text_size=14, keyboard_type=ft.KeyboardType.NUMBER,
        )

        def read_number(field):
            return float(str(field.value or "").strip().replace(",", "."))

        def add_position(_):
            try:
                quantity = max(
                    1, int(float(str(add_quantity.value or "1").replace(",", ".")))
                )
                if party_type == "Пиломатериал":
                    thickness = read_number(add_fields["thickness_cm"])
                    width = read_number(add_fields["width_cm"])
                    length = read_number(add_fields["length_m"])
                    if min(thickness, width, length) <= 0:
                        raise ValueError
                    item = {
                        "thickness_cm": thickness, "width_cm": width,
                        "length_m": length, "quantity": quantity,
                    }
                elif party_type == "Оцилиндровка":
                    diameter = int(read_number(add_fields["diameter_cm"]))
                    length = read_number(add_fields["length_m"])
                    if diameter <= 0 or length <= 0:
                        raise ValueError
                    item = {
                        "diameter_cm": diameter, "length_m": length,
                        "quantity": quantity,
                    }
                else:
                    diameter = int(read_number(add_fields["diameter"]))
                    length = read_number(add_fields["length"])
                    if diameter <= 0 or length <= 0:
                        raise ValueError
                    item = {
                        "diameter": diameter, "length": length,
                        "quantity": quantity, "price_per_m3": "0",
                        "cost": "0",
                    }
            except (TypeError, ValueError):
                position_error.value = "Проверьте размеры и количество."
                position_error.visible = True
                page.update()
                return
            position_error.visible = False
            apply_volume(item)
            items.append(item)
            for field in add_fields.values():
                field.value = ""
            add_quantity.value = "1"
            render_rows()
            page.update()

        def save(_):
            if not items:
                position_error.value = "Добавьте хотя бы одну позицию."
                position_error.visible = True
                page.update()
                return
            position_error.visible = False
            for item in items:
                apply_volume(item)
            update_party(
                party["id"], party["name"], party.get("description") or "",
                party.get("counterparty") or {}, items,
            )
            page.pop_dialog()
            refreshed = next(
                (p for p in list_parties() if p["id"] == party["id"]), None
            )
            if refreshed:
                show_party_detail(refreshed)

        render_rows()
        position_error = ft.Text(
            "", size=12, color="#B3261E", visible=False,
        )
        page.show_dialog(ft.AlertDialog(
            modal=True,
            # Системный «Назад» не должен закрывать редактор: только
            # «Отмена» или «Сохранить».
            data=BACK_BLOCKED,
            title=ft.Text("Изменить расчёты"),
            content=ft.Container(
                width=min(
                    max((getattr(page, "width", None) or 420) - 16, 300), 600,
                ),
                height=min(
                    (getattr(page, "height", None) or 760) * 0.74, 620,
                ),
                content=ft.Column(
                    tight=True, spacing=10, scroll=ft.ScrollMode.AUTO,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    controls=[
                        ft.Text(
                            "Количество можно изменить прямо в позиции. "
                            "Новые позиции добавляются ниже.",
                            size=12, color=TEXT,
                        ),
                        rows_column,
                        ft.Divider(height=1, color="#E4E8E4"),
                        ft.Text("Добавить позицию", size=14, color=GREEN,
                                weight=ft.FontWeight.BOLD),
                        ft.Row(wrap=True, spacing=6, run_spacing=6,
                               controls=list(add_fields.values())),
                        ft.Row(controls=[add_quantity, ft.Container(expand=True)]),
                        ft.Row(controls=[
                            ft.OutlinedButton(
                                "Добавить позицию", icon=ft.Icons.ADD,
                                on_click=add_position,
                            ),
                        ]),
                        position_error,
                    ],
                ),
            ),
            inset_padding=ft.Padding.symmetric(horizontal=8, vertical=8),
            actions=[
                ft.TextButton("Отмена", on_click=lambda _: page.pop_dialog()),
                ft.FilledButton(
                    "Сохранить", on_click=save,
                    style=ft.ButtonStyle(bgcolor=GREEN, color="white"),
                ),
            ],
        ))

    def open_party_editor(party):
        name = ft.TextField(label="Название", value=party["name"])
        description = ft.TextField(label="Описание", value=party["description"],
                                   multiline=True, max_length=500)
        cp = party.get("counterparty") or {}
        counterparty_select = ft.Dropdown(
            label="Контрагент",
            hint_text="Выберите из списка",
            options=[
                ft.DropdownOption(key=str(item["id"]), text=item["name"])
                for item in list_counterparties()
            ],
        )
        cp_name = ft.TextField(label="Название контрагента", value=cp.get("name", ""))
        cp_phone = ft.TextField(label="Телефон", value=cp.get("phone", ""))
        cp_email = ft.TextField(label="Email", value=cp.get("email", ""))
        cp_info = ft.TextField(label="Дополнительная информация", value=cp.get("info", ""))
        counterparty_status = ft.Text("", color=GREEN, size=12)

        def on_counterparty_select(e):
            selected = next(
                (item for item in list_counterparties()
                 if str(item["id"]) == e.control.value),
                None,
            )
            counterparty_status.value = ""
            if selected:
                cp_name.value = selected["name"]
                cp_phone.value = selected["phone"]
                cp_email.value = selected["email"]
                cp_info.value = selected["info"]
                cp_name.error_text = None
            page.update()

        counterparty_select.on_select = on_counterparty_select

        def save_counterparty_click(_):
            was_existing = find_counterparty_by_name(cp_name.value) is not None
            try:
                counterparty_id = save_counterparty(
                    cp_name.value, cp_phone.value, cp_email.value, cp_info.value,
                )
            except ValueError as exc:
                cp_name.error_text = str(exc)
                counterparty_status.value = ""
                page.update()
                return
            cp_name.error_text = None
            counterparty_select.options = [
                ft.DropdownOption(key=str(item["id"]), text=item["name"])
                for item in list_counterparties()
            ]
            counterparty_select.value = str(counterparty_id)
            counterparty_status.value = (
                "Контрагент обновлён" if was_existing else "Контрагент сохранён"
            )
            page.update()

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
            content=ft.Container(
                width=min(
                    max((getattr(page, "width", None) or 420) - 16, 300), 600,
                ),
                height=min(
                    (getattr(page, "height", None) or 760) * 0.74, 620,
                ),
                content=ft.Column(
                    tight=True, scroll=ft.ScrollMode.AUTO, spacing=10,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    controls=[
                        name, description, counterparty_select,
                        cp_name, cp_phone, cp_email, cp_info,
                        ft.Row(controls=[
                            ft.OutlinedButton(
                                "Сохранить контрагента",
                                icon=ft.Icons.PERSON_ADD_ALT_1_OUTLINED,
                                on_click=save_counterparty_click,
                            ),
                        ]),
                        counterparty_status,
                    ],
                ),
            ),
            inset_padding=ft.Padding.symmetric(horizontal=8, vertical=8),
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

    def guide_card(article: Article):
        """Карточка статьи в списке: большая обложка + заголовок и подзаголовок."""
        size = 116
        return ft.Container(
            bgcolor=GUIDE_CARD,
            border_radius=20,
            border=ft.Border.all(1, GUIDE_BORDER),
            padding=ft.Padding.all(10),
            on_click=lambda e, a=article: show_article(a),
            content=ft.Row(
                spacing=14,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Container(
                        width=size, height=size, border_radius=16,
                        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                        bgcolor="#EDE7D8",
                        content=guide_image(
                            article.cover, size, height=size, radius=16
                        ),
                    ),
                    ft.Column(
                        spacing=6, expand=True,
                        controls=[
                            ft.Text(
                                article.title, size=20,
                                weight=ft.FontWeight.W_700, color=GUIDE_INK,
                            ),
                            ft.Text(article.subtitle, size=14,
                                    color=GUIDE_MUTED),
                        ],
                    ),
                ],
            ),
        )

    def guide_disclaimer(width=None):
        """Небольшая справка под всеми материалами справочника."""
        return ft.Row(
            alignment=ft.MainAxisAlignment.CENTER,
            controls=[
                ft.Container(
                    width=width,
                    padding=ft.Padding.only(
                        left=20, right=20, top=10, bottom=26
                    ),
                    content=ft.Column(
                        spacing=10,
                        controls=[
                            ft.Row(
                                spacing=4,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                controls=[
                                    ft.Text(
                                        DISCLAIMER_TITLE,
                                        style=ft.TextStyle(
                                            size=16,
                                            weight=ft.FontWeight.BOLD,
                                            color="#7C8279",
                                            letter_spacing=1.4,
                                        ),
                                    ),
                                ],
                            ),
                            ft.Text(DISCLAIMER_TEXT, size=14, color="#5F665E"),
                        ],
                    ),
                ),
            ],
        )

    def show_reference():
        allow_screen_sleep(page)
        navigator.reset("/reference", show_reference)
        page.controls.clear()
        page.bgcolor = GUIDE_BG
        page.appbar = ft.AppBar(
            title=ft.Text("Справочник", weight=ft.FontWeight.W_600),
            bgcolor=GREEN,
            color="white",
            center_title=True,
        )
        page.navigation_bar = bottom_navigation(2)

        page_width = getattr(page, "width", None) or 420
        content_width = min(page_width, 760)

        page.add(
            ft.Container(
                expand=True, bgcolor=GUIDE_BG,
                content=ft.Column(
                    expand=True, spacing=0,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    scroll=ft.ScrollMode.AUTO,
                    controls=[
                        ft.Row(
                            alignment=ft.MainAxisAlignment.CENTER,
                            controls=[
                                ft.Container(
                                    width=content_width,
                                    padding=ft.Padding.only(
                                        left=14, right=14, top=16
                                    ),
                                    content=ft.Column(
                                        spacing=12,
                                        controls=[
                                            guide_card(article)
                                            for article in load_articles()
                                            if article.active
                                        ],
                                    ),
                                ),
                            ],
                        ),
                        guide_disclaimer(content_width),
                    ],
                ),
            )
        )
        page.update()

    def show_gost_table():
        """Таблица 1 ГОСТ 2708-75: объём бревна по толщине верхнего торца."""
        allow_screen_sleep(page)
        navigator.push("/reference/gost-table/table", show_gost_table)
        page.controls.clear()
        page.navigation_bar = None
        page.bgcolor = GUIDE_BG

        def back_to_article(_=None):
            article = article_by_slug("gost-table")
            if article is not None:
                show_article(article)
            else:
                show_reference()

        page.appbar = ft.AppBar(
            leading=ft.IconButton(
                ft.Icons.ARROW_BACK, on_click=back_to_article
            ),
            title=ft.Text("ГОСТ 2708-75", size=18),
            bgcolor=GREEN,
            color="white",
            center_title=True,
        )

        # В оригинальной таблице до 14 см идут все толщины, дальше — только
        # чётные: нечётные значения выше 14 см были досчитаны, их не показываем.
        diameters = [
            diameter
            for diameter in sorted(GOST_TABLE, key=int)
            if int(diameter) <= 14 or int(diameter) % 2 == 0
        ]
        # Кнопки длин — по полметра: 1 м, 1,5 м, 2 м и так далее.
        lengths = [
            f"{step / 2:.1f}"
            for step in range(2, 20)
            if any(f"{step / 2:.1f}" in row for row in GOST_TABLE.values())
        ]
        selected = {"length": "6.0" if "6.0" in lengths else lengths[-1]}

        def ru(value):
            return value.replace(".", ",")

        def length_label(length):
            # Целые метры показываем без дробной части: «2 м», а не «2,0 м».
            return ru(length.removesuffix(".0"))

        def volume_label(value):
            return ru(f"{float(value):g}")

        def pieces_label(value):
            try:
                pieces = 1 / float(value)
            except (TypeError, ValueError, ZeroDivisionError):
                return "—"
            return ru(f"{pieces:.1f}").removesuffix(",0")

        rows_host = ft.Column(spacing=0)
        chips_row = ft.Row(spacing=8, scroll=ft.ScrollMode.AUTO)
        subtitle = ft.Text(size=15)

        def render_subtitle():
            subtitle.spans = [
                ft.TextSpan(
                    "Объём бревна длиной ",
                    style=ft.TextStyle(size=15, color=GUIDE_MUTED),
                ),
                ft.TextSpan(
                    f"{length_label(selected['length'])} м",
                    style=ft.TextStyle(
                        size=15, color=GUIDE_INK,
                        weight=ft.FontWeight.BOLD,
                    ),
                ),
            ]

        def select_length(length):
            selected["length"] = length
            render_subtitle()
            render_chips()
            render_rows()

        def chip(length):
            active = length == selected["length"]
            return ft.Container(
                padding=ft.Padding.symmetric(horizontal=16, vertical=10),
                bgcolor=GUIDE_CARD if active else "transparent",
                border=ft.Border.all(
                    1, GREEN if active else GUIDE_BORDER
                ),
                border_radius=12,
                on_click=lambda _, value=length: select_length(value),
                content=ft.Text(
                    f"{length_label(length)} м", size=15,
                    color=GUIDE_INK if active else GUIDE_MUTED,
                    weight=ft.FontWeight.BOLD if active else None,
                ),
            )

        def render_chips():
            chips_row.controls = [chip(length) for length in lengths]
            page.update()

        def header():
            return ft.Container(
                padding=ft.Padding.only(left=14, right=14, top=10, bottom=10),
                content=ft.Row(
                    controls=[
                        ft.Text(
                            "ТОЛЩИНА", size=12, color=GUIDE_MUTED,
                            expand=3,
                        ),
                        ft.Text(
                            "1 БРЕВНО, М³", size=12, color=GUIDE_MUTED,
                            expand=3, text_align=ft.TextAlign.CENTER,
                        ),
                        ft.Text(
                            "ШТ В 1 М³", size=12, color=GUIDE_MUTED,
                            expand=3, text_align=ft.TextAlign.RIGHT,
                        ),
                    ],
                ),
            )

        def data_row(index, diameter):
            value = GOST_TABLE[diameter].get(selected["length"])
            return ft.Container(
                padding=ft.Padding.symmetric(horizontal=14, vertical=14),
                bgcolor=GUIDE_CARD if index % 2 == 0 else "transparent",
                content=ft.Row(
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Text(
                            f"{diameter} см", size=17,
                            weight=ft.FontWeight.BOLD, color=GUIDE_INK,
                            expand=3, selectable=True,
                        ),
                        ft.Text(
                            volume_label(value) if value is not None else "—",
                            size=17, weight=ft.FontWeight.BOLD,
                            color=GUIDE_INK if value is not None else "#B9B3A4",
                            expand=3, text_align=ft.TextAlign.CENTER,
                            selectable=True,
                        ),
                        ft.Text(
                            pieces_label(value) if value is not None else "—",
                            size=16, color=GUIDE_MUTED,
                            expand=3, text_align=ft.TextAlign.RIGHT,
                            selectable=True,
                        ),
                    ],
                ),
            )

        def render_rows():
            rows_host.controls = [header()] + [
                data_row(index, diameter)
                for index, diameter in enumerate(diameters)
            ]
            page.update()

        page.add(
            ft.Container(
                expand=True, bgcolor=GUIDE_BG,
                content=ft.Column(
                    expand=True, spacing=0,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    controls=[
                        ft.Container(
                            padding=ft.Padding.only(
                                left=14, right=14, top=14, bottom=6
                            ),
                            content=subtitle,
                        ),
                        ft.Container(
                            padding=ft.Padding.only(left=14, right=14),
                            content=chips_row,
                        ),
                        ft.Container(
                            padding=ft.Padding.only(
                                left=14, right=14, top=8, bottom=4
                            ),
                            content=ft.Text(
                                "Диаметр — верхний торец в см. "
                                "Прочерк — значения в таблице нет.",
                                size=12, color=GUIDE_MUTED,
                            ),
                        ),
                        ft.Container(
                            expand=True,
                            margin=ft.Margin.only(top=4),
                            content=ft.Column(
                                expand=True,
                                scroll=ft.ScrollMode.AUTO,
                                controls=[rows_host],
                            ),
                        ),
                    ],
                ),
            )
        )
        render_subtitle()
        render_chips()
        render_rows()

    def show_article(article: Article):
        """Экран статьи: шапка с картинкой и Markdown-текст под ней."""
        allow_screen_sleep(page)
        navigator.push(
            f"/reference/{article.slug}",
            lambda: show_article(article),
        )
        page.controls.clear()
        page.appbar = None
        page.navigation_bar = None
        page.bgcolor = GUIDE_BG

        page_width = getattr(page, "width", None) or 420
        # На планшете и в вебе не растягиваем статью на всю ширину окна.
        hero_width = min(page_width, 760)
        hero_height = GUIDE_HERO_HEIGHT if page_width < 700 else 380
        body_width = max(240, hero_width - 36)

        hero = ft.Container(
            width=hero_width,
            height=hero_height,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            content=ft.Stack(
                width=hero_width,
                height=hero_height,
                controls=[
                    guide_image(
                        article.hero, hero_width,
                        height=hero_height, radius=0,
                    ),
                    # Плавный переход от картинки к цвету страницы, чтобы
                    # заголовок читался на любом фоне.
                    ft.Container(
                        left=0, right=0, bottom=0,
                        height=hero_height * 0.62,
                        gradient=ft.LinearGradient(
                            begin=ft.Alignment.TOP_CENTER,
                            end=ft.Alignment.BOTTOM_CENTER,
                            colors=["#00FBF6E9", "#D9FBF6E9", GUIDE_BG],
                        ),
                    ),
                    ft.Container(
                        left=20, right=20, bottom=18,
                        content=ft.Column(
                            spacing=6,
                            controls=[
                                ft.Text(
                                    article.title, size=28,
                                    weight=ft.FontWeight.BOLD,
                                    color=GUIDE_INK, selectable=True,
                                ),
                                ft.Text(article.subtitle, size=15,
                                        color="#4E574E", selectable=True),
                            ],
                        ),
                    ),
                ],
            ),
        )

        body_controls = guide_markdown_controls(
            load_article_body(article), body_width
        )
        if article.slug == "gost-table":
            body_controls.insert(
                0, guide_table_button(lambda _: show_gost_table())
            )

        body = ft.Row(
            alignment=ft.MainAxisAlignment.CENTER,
            controls=[
                ft.Container(
                    width=hero_width,
                    bgcolor=GUIDE_BG,
                    padding=ft.Padding.only(
                        left=18, right=18, top=18, bottom=30
                    ),
                    content=ft.Column(
                        spacing=14,
                        controls=body_controls,
                    ),
                ),
            ],
        )

        back_button = ft.Container(
            left=14, top=14, width=44, height=44, border_radius=22,
            bgcolor="#E0144A36",
            alignment=ft.Alignment.CENTER,
            shadow=ft.BoxShadow(blur_radius=12, color="#33000000"),
            on_click=lambda _: show_reference(),
            content=ft.Icon(ft.Icons.ARROW_BACK, color="#F6F1E2", size=22),
        )

        page.add(
            ft.Stack(
                expand=True,
                controls=[
                    ft.Column(
                        expand=True, spacing=0,
                        scroll=ft.ScrollMode.AUTO,
                        controls=[
                            ft.Row(
                                alignment=ft.MainAxisAlignment.CENTER,
                                controls=[hero],
                            ),
                            body,
                        ],
                    ),
                    back_button,
                ],
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
        navigator.push("/gost", show_gost_calculator)
        page.controls.clear()
        page.navigation_bar = None
        active_tab["value"] = "table"

        draft = load_screen_state("gost")
        saved_settings = draft.get("settings") or {}
        if not isinstance(saved_settings, dict):
            saved_settings = {}
        if not saved_settings:
            # Settings outlive a saved calculation, so they are kept in their
            # own draft that is not cleared together with the items.
            saved_settings = load_screen_state("gost_settings")
        if not isinstance(saved_settings, dict):
            saved_settings = {}
        settings = load_settings(saved_settings)

        # The number is derived from the saved parties, so a new calculation
        # gets the next number after the previous one was saved.
        calculation_number = sum(
            1 for party in list_parties() if party["type"] == "ГОСТ"
        ) + 1

        page.appbar = ft.AppBar(
            leading=ft.IconButton(ft.Icons.ARROW_BACK, on_click=lambda _: show_home()),
            title=ft.Text(
                f"Расчет #{calculation_number}\n(ГОСТ-75-Табл.1)",
                size=16, text_align=ft.TextAlign.CENTER,
            ),
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

        total_volume = ft.Text("0.000 м³", size=25, color=ORANGE,
                               weight=ft.FontWeight.BOLD)
        total_count = ft.Text("0 шт.", size=17, color=TEXT)
        items_column = ft.Column(spacing=7, scroll=ft.ScrollMode.AUTO, expand=True)
        table_view = ft.Row(spacing=8, expand=True,
                            vertical_alignment=ft.CrossAxisAlignment.STRETCH)
        content_host = ft.Container(expand=True, content=table_view)

        def format_gost_volume(value):
            # ГОСТ-объёмы показываем и округляем до 0.001 м³.
            quantum = Decimal("0.001")
            return f"{value.quantize(quantum, rounding=ROUND_HALF_UP):.3f}"

        # Restore the draft so the calculation survives an app/phone restart.
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
                "settings": settings,
            })
            save_screen_state("gost_settings", settings)

        def confirm_delete_records():
            def delete(_):
                current_items.clear()
                save_state()
                page.pop_dialog()
                refresh_items()
                summary.refresh()

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
                current_items.clear()
                settings.clear()
                settings.update(default_settings())
                save_state()
                page.pop_dialog()
                refresh_diameter_grid()
                refresh_items()
                summary.refresh()

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

        def refresh_summary():
            summary.refresh()

        def recalc_item(item):
            """Recompute the ГОСТ volume for the current quantity."""
            try:
                volume = calculate_gost_item(
                    item["diameter"],
                    Decimal(str(item["length"])),
                    item["quantity"],
                    GOST_TABLE,
                )
            except ValueError:
                return
            item["volume"] = volume
            item["display_volume"] = format_gost_volume(volume)

        def open_quantity_dialog(index):
            if not 0 <= index < len(current_items):
                return
            item = current_items[index]
            label = f"Ø{item['diameter']} {float(item['length']):g}м"

            def apply(quantity):
                item["quantity"] = quantity
                recalc_item(item)
                refresh_items()

            ask_quantity(page, label, item["quantity"], apply)

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
                        on_click=lambda e, i=index: open_quantity_dialog(i),
                        content=ft.Row(
                            spacing=7,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            controls=[
                                ft.Container(
                                    width=48, height=54, border_radius=10,
                                    bgcolor="#F5F6F6", alignment=ft.Alignment.CENTER,
                                    content=ft.Text(
                                        f"Ø{item['diameter']}", size=18,
                                        weight=ft.FontWeight.W_600, color=TEXT,
                                        no_wrap=True,
                                    ),
                                ),
                                ft.Column(
                                    spacing=1, expand=True,
                                    controls=[
                                        ft.Text(
                                            f"{format_length(item['length'])} м",
                                            size=13, color=TEXT, no_wrap=True,
                                            overflow=ft.TextOverflow.ELLIPSIS,
                                        ),
                                        ft.Text(
                                            f"{item['quantity']} шт.", size=13,
                                            color=TEXT, no_wrap=True,
                                            overflow=ft.TextOverflow.ELLIPSIS,
                                        ),
                                    ],
                                ),
                                ft.Column(
                                    spacing=0,
                                    horizontal_alignment=ft.CrossAxisAlignment.END,
                                    controls=[
                                        ft.Text(f"{item['display_volume']}",
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
            length = selected_length["value"]
            # Logs with the same diameter and length are one position.
            for item in current_items:
                if item["diameter"] == diameter and item["length"] == length:
                    item["quantity"] += 1
                    recalc_item(item)
                    refresh_items()
                    vibrate(page)
                    return
            length_decimal = Decimal(str(length))
            try:
                volume = calculate_gost_item(
                    diameter, length_decimal, 1, GOST_TABLE
                )
            except ValueError:
                show_missing_table_value(diameter, length)
                return
            current_items.append({
                "diameter": diameter,
                "length": length,
                "quantity": 1,
                "volume": volume,
                "display_volume": format_gost_volume(volume),
            })
            refresh_items()
            vibrate(page)

        def party_payload():
            payload = []
            for item in current_items:
                price, price_range = price_for_diameter(
                    settings, item["diameter"]
                )
                payload.append({
                    **item,
                    "volume": str(item["volume"]),
                    "price_per_m3": str(price) if price is not None else "0",
                    "range_from": price_range["from"] if price_range else None,
                    "range_to": price_range["to"] if price_range else None,
                    "species": settings["species"],
                    "calc_type": settings["calc_type"],
                    "cost": (
                        str(item["volume"] * price)
                        if price is not None else "0"
                    ),
                })
            return payload

        def save_gost_party(_):
            if not current_items:
                page.show_dialog(ft.SnackBar(
                    content=ft.Text("Сначала добавьте хотя бы одно бревно."),
                ))
                return
            create_party(
                "ГОСТ",
                f"Кругляк {party_date()}",
                party_payload(),
                preset_counterparty=settings["counterparty"] or None,
                preset_description=(
                    f"Порода: {settings['species']}. "
                    f"Тип расчёта: {settings['calc_type']}."
                ),
            )

        def apply_settings_changes():
            refresh_diameter_grid()
            refresh_items()

        def show_diameter_warning(_value=None):
            def close(_):
                page.pop_dialog()
                page.update()

            page.show_dialog(ft.AlertDialog(
                modal=True,
                icon=ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED,
                             color=ORANGE, size=36),
                title=ft.Text("Важно", size=22,
                              weight=ft.FontWeight.BOLD),
                content=ft.Column(
                    tight=True, spacing=12,
                    controls=[
                        ft.Text("ГОСТ-2708-75 таблица №1:",
                                size=15, weight=ft.FontWeight.BOLD),
                        ft.Text(
                            "значения кубатуры для нечетных диаметров "
                            "размером от 15 см являются расчетными, т.к. "
                            "в ГОСТе представлены значения только для "
                            "четных диаметров (от 14 см).",
                            size=15,
                        ),
                        ft.Text(
                            "Значение для нечетного диаметра рассчитывается "
                            "как среднее от 2х крайних значений четных "
                            "диаметров. Например:",
                            size=15,
                        ),
                        ft.Text(
                            "V(D.15) = ( V(D.14) + V(D.16) ) / 2",
                            size=15,
                        ),
                    ],
                ),
                actions=[
                    ft.TextButton(
                        "Закрыть", on_click=close,
                        style=ft.ButtonStyle(
                            color="#4F5559",
                            text_style=ft.TextStyle(
                                size=17, weight=ft.FontWeight.BOLD,
                            ),
                        ),
                    ),
                ],
                actions_alignment=ft.MainAxisAlignment.CENTER,
            ))

        summary = CalculationSummary(
            page,
            settings=settings,
            number=calculation_number,
            title=f"Расчет #{calculation_number} (ГОСТ-75-Табл.1)",
            get_items=lambda: current_items,
            digits=3,
            on_save=save_gost_party,
            on_settings_changed=apply_settings_changes,
            on_filter_changed=show_diameter_warning,
        )

        def choose_tab(tab_name):
            active_tab["value"] = tab_name
            is_table = tab_name == "table"
            content_host.content = table_view if is_table else summary.view
            bottom_host.content = table_actions if is_table else summary.actions
            volume_row.visible = is_table
            summary.totals.visible = not is_table
            if is_table:
                summary.totals.content = None
            table_tab.style = calc_tab_style(GREEN, is_table)
            summary_tab.style = calc_tab_style(GREEN, not is_table)
            if not is_table:
                refresh_summary()
            save_state()
            page.update()

        def back_from_summary():
            """«Назад» с «Итогов» возвращает к таблице расчёта."""
            if active_tab["value"] != "summary":
                return False
            choose_tab("table")
            return True

        navigator.on_screen_back(back_from_summary)

        def open_length_picker(_):
            length_input = ft.TextField(
                label="Длина, м", value=f"{selected_length['value']:.1f}",
                keyboard_type=ft.KeyboardType.NUMBER, autofocus=True,
            )
            length_error = ft.Text(
                "", size=12, color="#B3261E", visible=False,
            )

            def set_length(_):
                try:
                    value = float(length_input.value.replace(",", "."))
                    if value <= 0:
                        raise ValueError
                except (TypeError, ValueError, AttributeError):
                    length_error.value = "Введите корректную длину больше нуля."
                    length_error.visible = True
                    page.update()
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
                    length_error,
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

        def make_diameter_button(diameter):
            return ft.FilledButton(
                content=ft.Text(str(diameter), size=22, no_wrap=True,
                                text_align=ft.TextAlign.CENTER),
                height=72,
                style=ft.ButtonStyle(
                    bgcolor="#E5E6E7", color=TEXT,
                    padding=ft.Padding.symmetric(horizontal=2, vertical=4),
                    shape=ft.RoundedRectangleBorder(radius=0), elevation=0,
                ),
                on_click=lambda e, n=diameter: add_diameter(n),
            )

        diameter_buttons = {
            diameter: make_diameter_button(diameter)
            for diameter in DIAMETERS
        }
        diameter_grid = ft.GridView(
            expand=True, runs_count=diameter_grid_columns(page),
            spacing=5, run_spacing=5, child_aspect_ratio=1.08,
            controls=[],
        )

        def refresh_diameter_grid():
            mode = settings["diameter_filter"]
            diameter_grid.controls.clear()
            for diameter in DIAMETERS:
                if mode == "even" and diameter % 2:
                    continue
                if mode == "odd" and diameter % 2 == 0:
                    continue
                diameter_grid.controls.append(diameter_buttons[diameter])

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
            "Таблица", expand=True, height=TAB_BAR_HEIGHT,
            on_click=lambda _: choose_tab("table"),
            style=calc_tab_style(GREEN, True),
        )
        summary_tab = ft.TextButton(
            "Итоги", expand=True, height=TAB_BAR_HEIGHT,
            on_click=lambda _: choose_tab("summary"),
            style=calc_tab_style(GREEN, False),
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

        table_actions = ft.Container(
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
        )
        bottom_host = ft.Container(content=table_actions)

        volume_row = ft.Container(
            padding=ft.Padding.symmetric(horizontal=12, vertical=7),
            content=ft.Row(controls=[
                ft.IconButton(
                    ft.Icons.TUNE, icon_color="#85898C", icon_size=25,
                    tooltip="Настройки расчёта",
                    on_click=summary.open_settings,
                ),
                total_volume,
                ft.Container(expand=True),
                total_count,
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
        )

        page.add(ft.Column(
            spacing=0, expand=True,
            controls=[
                calc_tab_bar(GREEN, [table_tab, summary_tab]),
                volume_row,
                ft.Container(content=content_host, expand=True,
                             padding=ft.Padding.symmetric(horizontal=8)),
                summary.totals,
                bottom_host,
            ],
        ))
        refresh_diameter_grid()
        refresh_items()
        choose_tab(active_tab["value"])
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
        navigator.push("/lumber", show_lumber_calculator)
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

        summary_volume = ft.Text("0.0000 м³", size=24, color=ORANGE,
                                  weight=ft.FontWeight.BOLD)
        summary_details = ft.Text("0 шт. 0.00 RUB.", size=14, color=TEXT)
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
            value=ROUNDING_OPTIONS[rounding_digits["value"] - 1][0],
            width=110,
            dense=True,
            text_size=14,
            options=[
                ft.DropdownOption(key=value, text=text)
                for value, text in ROUNDING_OPTIONS
            ],
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

            # A brand-new position is pre-filled with "0" (dimensions, price)
            # and "1" (quantity). The first time such a field is focused the
            # whole value is selected, so the first typed digit replaces it
            # instead of appending ("05" -> "5"). Once the user types, normal
            # editing resumes and later digits append.
            is_new_record = index is None and duplicate is None
            touched_fields = set() if is_new_record else set(field_order)

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

            def select_all(key):
                field = fields.get(key)
                if field is None:
                    return
                length = len(str(field.value or ""))
                field.selection = ft.TextSelection(
                    base_offset=0, extent_offset=length
                )

            def focus_field(key):
                select_field(key)
                if is_new_record and key not in touched_fields:
                    select_all(key)
                    page.update()

            def change_field(key, text):
                if is_new_record and key not in touched_fields:
                    touched_fields.add(key)
                    # The selected placeholder was replaced; collapse the
                    # selection at the end so later digits append normally.
                    caret = len(str(text or ""))
                    fields[key].selection = ft.TextSelection(
                        base_offset=caret, extent_offset=caret
                    )
                apply_field_value(key, text)

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
                    autofocus=(key == focus),
                    border=ft.InputBorder.NONE, text_size=16,
                    text_align=ft.TextAlign.START, expand=True,
                    bgcolor="#FFFFFF",
                    on_focus=lambda e, k=key: focus_field(k),
                    on_change=lambda e, k=key: change_field(
                        k, e.control.value
                    ),
                )
                fields[key] = field
                unit_label = (
                    UNIT_NAMES[unit_modes[key]["value"]]
                    if key in unit_modes else default_unit
                )
                unit_control = ft.Text(
                    unit_label, size=14, color="#171A18", width=60, text_align=ft.TextAlign.CENTER,
                )
                unit_texts[key] = unit_control
                row = ft.Container(
                    height=40,
                    padding=ft.Padding.symmetric(horizontal=2, vertical=0),
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

            editor_error = ft.Text(
                "", size=12, color="#B3261E", visible=False,
            )

            def commit(_):
                # Перед сохранением подхватываем актуальный текст полей:
                # значения могли быть изменены без события on_change.
                for key in field_order:
                    if not apply_field_value(key, fields[key].value, refresh=False):
                        editor_error.value = "Проверьте размеры, количество и цену."
                        editor_error.visible = True
                        page.update()
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
                    editor_error.value = "Проверьте размеры, количество и цену."
                    editor_error.visible = True
                    page.update()
                    return
                editor_error.visible = False
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
                    editor_error,
                    ft.Row(
                        alignment=ft.MainAxisAlignment.CENTER,
                        controls=[
                            ft.FilledButton(
                                "OK", height=44, width=160,
                                style=ft.ButtonStyle(
                                    bgcolor="#E77C3B", color="white"
                                ),
                                on_click=commit,
                            ),
                        ],
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
            # The autofocused field is already selected when the keyboard
            # opens, so the placeholder "0"/"1" is replaced by the first digit.
            if is_new_record:
                select_all(focus)
                page.update()

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

    show_home()


if __name__ == "__main__":
    ft.run(main, assets_dir="assets")
