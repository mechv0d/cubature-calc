"""Summary screen, calculation settings and Excel export."""

import asyncio
from decimal import Decimal
from io import BytesIO

import flet as ft
import pytest
from openpyxl import load_workbook
from test_app_smoke import (
    FakePage,
    all_controls,
    find_button,
    open_gost_screen,
    text_of,
    walk,
)

from app import storage
from app.calculators.gost_2708 import calculate_gost_item, load_gost_table
from app.excel_export import build_calculation_xlsx
from main import main


def open_summary(page):
    summary_tab = next(
        control for control in all_controls(page)
        if isinstance(control, ft.TextButton)
        and text_of(control) == "Итоги"
    )
    summary_tab.on_click(None)


def test_summary_has_totals_and_actions(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.sqlite3")
    page = FakePage()
    main(page)
    open_gost_screen(page)
    find_button(page, "14").on_click(None)
    open_summary(page)

    controls = list(all_controls(page))
    assert any(
        isinstance(control, ft.Text) and control.value == "Итоговая кубатура"
        for control in controls
    )
    assert any(
        isinstance(control, ft.Text) and control.value == "Общая стоимость"
        for control in controls
    )
    assert any(
        isinstance(control, ft.Text) and control.value == "[12-17]"
        for control in controls
    )
    assert any(
        isinstance(control, ft.FilledButton)
        and "Сохранить расчёт" in text_of(control)
        for control in controls
    )
    assert any(
        isinstance(control, ft.OutlinedButton)
        and "Отправить" in text_of(control)
        for control in controls
    )
    assert any(
        isinstance(control, ft.OutlinedButton)
        and "Скачать" in text_of(control)
        for control in controls
    )


def test_info_button_shows_calculation_details(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.sqlite3")
    page = FakePage()
    main(page)
    open_gost_screen(page)
    find_button(page, "14").on_click(None)
    find_button(page, "20").on_click(None)
    open_summary(page)

    info_button = next(
        control for control in all_controls(page)
        if isinstance(control, ft.OutlinedButton) and control.width == 52
    )
    info_button.on_click(None)

    dialog = page.dialogs[-1]
    assert isinstance(dialog, ft.AlertDialog)
    assert dialog.title.value == "РАСЧЕТ # 1"
    texts = [
        control.value for control in walk(dialog)
        if isinstance(control, ft.Text)
    ]
    assert "Количество бревен:" in texts
    assert "2 шт." in texts
    assert "Ø max:" in texts
    assert "20 см" in texts
    assert "Ø средний:" in texts
    assert "17.0 см" in texts
    assert "Контрагент:" in texts
    assert "н/д" in texts


def test_settings_filter_diameters_and_set_price(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.sqlite3")
    page = FakePage()
    main(page)
    open_gost_screen(page)

    settings_button = next(
        control for control in all_controls(page)
        if isinstance(control, ft.IconButton)
        and control.tooltip == "Настройки расчёта"
    )
    settings_button.on_click(None)
    dialog = page.dialogs[-1]
    assert isinstance(dialog, ft.AlertDialog)
    assert dialog.title.value == "Настройки расчёта"

    filter_dropdown = next(
        control for control in walk(dialog)
        if isinstance(control, ft.Dropdown)
        and control.label == "Показ диаметров"
    )
    filter_dropdown.value = "even"
    price_fields = [
        control for control in walk(dialog)
        if isinstance(control, ft.TextField)
        and control.hint_text == "цена"
    ]
    price_fields[1].value = "2000"
    next(
        control for control in walk(dialog)
        if isinstance(control, ft.FilledButton)
        and text_of(control) == "Применить"
    ).on_click(None)

    assert not any(
        isinstance(control, ft.FilledButton) and text_of(control) == "5"
        for control in all_controls(page)
    )
    assert any(
        isinstance(control, ft.FilledButton) and text_of(control) == "6"
        for control in all_controls(page)
    )

    find_button(page, "14").on_click(None)
    open_summary(page)
    assert any(
        isinstance(control, ft.Text) and control.value == "246.00"
        for control in all_controls(page)
    )
    assert any(
        isinstance(control, ft.Text) and control.value == "246.00 RUB."
        for control in all_controls(page)
    )


def open_settings(page):
    button = next(
        control for control in all_controls(page)
        if isinstance(control, ft.IconButton)
        and control.tooltip == "Настройки расчёта"
    )
    button.on_click(None)
    return page.dialogs[-1]


def apply_settings(dialog):
    next(
        control for control in walk(dialog)
        if isinstance(control, ft.FilledButton)
        and text_of(control) == "Применить"
    ).on_click(None)


def test_settings_validation_error_is_shown_inside_dialog(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.sqlite3")
    page = FakePage()
    main(page)
    open_gost_screen(page)
    dialog = open_settings(page)
    dialogs_before = len(page.dialogs)

    # Make two ranges overlap: the dialog must stay open and show the error
    # inline instead of a SnackBar that would be hidden under the modal.
    starts = [
        control for control in walk(dialog)
        if isinstance(control, ft.TextField) and control.hint_text == "от"
    ]
    ends = [
        control for control in walk(dialog)
        if isinstance(control, ft.TextField) and control.hint_text == "до"
    ]
    starts[1].value = "10"
    ends[1].value = "20"
    apply_settings(dialog)

    assert len(page.dialogs) == dialogs_before
    assert isinstance(page.dialogs[-1], ft.AlertDialog)
    errors = [
        control for control in walk(dialog)
        if isinstance(control, ft.Text)
        and "пересекаться" in str(control.value)
    ]
    assert errors and errors[0].visible


def test_changing_diameter_filter_shows_important_notice(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.sqlite3")
    page = FakePage()
    main(page)
    open_gost_screen(page)
    dialog = open_settings(page)

    filter_dropdown = next(
        control for control in walk(dialog)
        if isinstance(control, ft.Dropdown)
        and control.label == "Показ диаметров"
    )
    filter_dropdown.value = "even"
    apply_settings(dialog)

    notice = page.dialogs[-1]
    assert isinstance(notice, ft.AlertDialog)
    assert notice.title.value == "Важно"
    texts = [
        control.value for control in walk(notice)
        if isinstance(control, ft.Text)
    ]
    assert "ГОСТ-2708-75 таблица №1:" in texts
    assert any("нечетных диаметров" in str(text) for text in texts)
    assert any("V(D.15)" in str(text) for text in texts)
    assert any(
        isinstance(control, ft.TextButton)
        and text_of(control) == "Закрыть"
        for control in walk(notice)
    )


def test_clear_calculation_resets_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.sqlite3")
    page = FakePage()
    main(page)
    open_gost_screen(page)
    find_button(page, "14").on_click(None)

    dialog = open_settings(page)
    filter_dropdown = next(
        control for control in walk(dialog)
        if isinstance(control, ft.Dropdown)
        and control.label == "Показ диаметров"
    )
    filter_dropdown.value = "odd"
    next(
        control for control in walk(dialog)
        if isinstance(control, ft.OutlinedButton)
        and text_of(control) == "Один диапазон"
    ).on_click(None)
    apply_settings(dialog)
    # Dismiss the ГОСТ notice about odd diameters.
    next(
        control for control in walk(page.dialogs[-1])
        if isinstance(control, ft.TextButton)
        and text_of(control) == "Закрыть"
    ).on_click(None)

    menu = next(
        action for action in page.appbar.actions
        if isinstance(action, ft.PopupMenuButton)
    )
    clear_item = next(
        item for item in menu.items
        if isinstance(item.content, ft.Text)
        and item.content.value == "Очистить расчёт"
    )
    clear_item.on_click(None)
    confirm = page.dialogs[-1]
    assert confirm.title.value == "Очистить расчёт?"
    next(
        control for control in walk(confirm)
        if isinstance(control, ft.TextButton) and text_of(control) == "Очистить"
    ).on_click(None)

    # Settings are back to defaults and the items are gone.
    dialog = open_settings(page)
    starts = [
        control for control in walk(dialog)
        if isinstance(control, ft.TextField) and control.hint_text == "от"
    ]
    assert [field.value for field in starts] == ["3", "12", "18"]
    filter_dropdown = next(
        control for control in walk(dialog)
        if isinstance(control, ft.Dropdown)
        and control.label == "Показ диаметров"
    )
    assert filter_dropdown.value == "all"
    assert not any(
        isinstance(control, ft.Text) and str(control.value).startswith("Ø14")
        for control in all_controls(page)
    )


def test_delete_records_keeps_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.sqlite3")
    page = FakePage()
    main(page)
    open_gost_screen(page)
    find_button(page, "14").on_click(None)

    dialog = open_settings(page)
    next(
        control for control in walk(dialog)
        if isinstance(control, ft.OutlinedButton)
        and text_of(control) == "Один диапазон"
    ).on_click(None)
    apply_settings(dialog)

    menu = next(
        action for action in page.appbar.actions
        if isinstance(action, ft.PopupMenuButton)
    )
    items = [
        item.content.value for item in menu.items
        if isinstance(item.content, ft.Text)
    ]
    assert items.index("Удалить записи") < items.index("Очистить расчёт")

    delete_item = next(
        item for item in menu.items
        if isinstance(item.content, ft.Text)
        and item.content.value == "Удалить записи"
    )
    delete_item.on_click(None)
    confirm = page.dialogs[-1]
    assert confirm.title.value == "Удалить записи?"
    next(
        control for control in walk(confirm)
        if isinstance(control, ft.TextButton) and text_of(control) == "Удалить"
    ).on_click(None)

    # Logs are gone, but the custom single range is preserved.
    assert not any(
        isinstance(control, ft.Text) and str(control.value).startswith("Ø14")
        for control in all_controls(page)
    )
    dialog = open_settings(page)
    starts = [
        control for control in walk(dialog)
        if isinstance(control, ft.TextField) and control.hint_text == "от"
    ]
    assert [field.value for field in starts] == ["3"]


def test_diameter_3_is_available_in_both_calculators(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.sqlite3")
    page = FakePage()
    main(page)
    open_gost_screen(page)
    find_button(page, "3").on_click(None)
    assert any(
        isinstance(control, ft.Text) and "Ø3" in str(control.value)
        for control in all_controls(page)
    )

    second = FakePage()
    main(second)
    tile = next(
        control for control in all_controls(second)
        if isinstance(control, ft.ListTile)
        and isinstance(control.title, ft.Text)
        and "Оцилиндровка" in control.title.value
    )
    tile.on_click(None)
    next(
        control for control in all_controls(second)
        if isinstance(control, ft.FilledButton) and text_of(control) == "3"
    ).on_click(None)
    assert any(
        isinstance(control, ft.Text) and "Ø3" in str(control.value)
        for control in all_controls(second)
    )


def test_summary_groups_rows_by_length(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.sqlite3")
    page = FakePage()
    main(page)
    open_gost_screen(page)
    find_button(page, "20").on_click(None)

    # Switch to another length and add another log.
    find_button(page, "ДЛИНА: 6").on_click(None)
    length_dialog = page.dialogs[-1]
    next(
        control for control in walk(length_dialog)
        if isinstance(control, ft.TextField)
    ).value = "4"
    next(
        control for control in walk(length_dialog)
        if isinstance(control, ft.FilledButton) and text_of(control) == "Применить"
    ).on_click(None)
    find_button(page, "22").on_click(None)

    open_summary(page)

    groups = [
        control.value for control in all_controls(page)
        if isinstance(control, ft.Text) and control.value == "[18-120]"
    ]
    # Two separate subtotals: one per length.
    assert len(groups) == 2
    lengths = [
        control.value for control in all_controls(page)
        if isinstance(control, ft.Text)
        and control.value in {"4.0", "6.0"}
    ]
    assert "4.0" in lengths and "6.0" in lengths


def find_item_container(page, label):
    for control in all_controls(page):
        if isinstance(control, ft.Container) and control.on_click is not None:
            texts = [
                child.value for child in walk(control)
                if isinstance(child, ft.Text)
            ]
            if any(label in str(text) for text in texts):
                return control
    raise AssertionError(f"item {label} not found")


def test_same_diameter_and_length_merges_into_one_row(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.sqlite3")
    page = FakePage()
    main(page)
    open_gost_screen(page)

    find_button(page, "30").on_click(None)
    find_button(page, "30").on_click(None)

    texts = [
        control.value for control in all_controls(page)
        if isinstance(control, ft.Text)
    ]
    # One row only, with quantity 2.
    assert texts.count("Ø30") == 1
    assert "2 шт." in texts
    expected = calculate_gost_item(30, Decimal(6), 2, load_gost_table())
    assert f"{expected:.3f} м³" in texts


def test_tapping_row_opens_quantity_dialog(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.sqlite3")
    page = FakePage()
    main(page)
    open_gost_screen(page)
    find_button(page, "20").on_click(None)

    find_item_container(page, "Ø20").on_click(None)

    dialog = page.dialogs[-1]
    assert isinstance(dialog, ft.AlertDialog)
    assert dialog.title.value == "Выберите количество Ø20 6м"
    quantity_field = next(
        control for control in walk(dialog)
        if isinstance(control, ft.TextField)
    )
    # Focused numeric field: the phone keyboard opens right away.
    assert quantity_field.autofocus is True
    assert quantity_field.keyboard_type == ft.KeyboardType.NUMBER
    assert quantity_field.value == "1"

    quantity_field.value = "3"
    next(
        control for control in walk(dialog)
        if isinstance(control, ft.FilledButton) and text_of(control) == "Сохранить"
    ).on_click(None)

    texts = [
        control.value for control in all_controls(page)
        if isinstance(control, ft.Text)
    ]
    assert "3 шт." in texts
    expected = calculate_gost_item(20, Decimal(6), 3, load_gost_table())
    assert f"{expected:.3f} м³" in texts


def test_typed_quantity_is_saved(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.sqlite3")
    page = FakePage()
    main(page)
    open_gost_screen(page)
    find_button(page, "20").on_click(None)

    find_item_container(page, "Ø20").on_click(None)

    dialog = page.dialogs[-1]
    quantity_field = next(
        control for control in walk(dialog)
        if isinstance(control, ft.TextField)
    )
    quantity_field.value = "12"

    next(
        control for control in walk(dialog)
        if isinstance(control, ft.FilledButton) and text_of(control) == "Сохранить"
    ).on_click(None)

    texts = [
        control.value for control in all_controls(page)
        if isinstance(control, ft.Text)
    ]
    assert "12 шт." in texts
    expected = calculate_gost_item(20, Decimal(6), 12, load_gost_table())
    assert f"{expected:.3f} м³" in texts


def test_quantity_dialog_rejects_out_of_range_input(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.sqlite3")
    page = FakePage()
    main(page)
    open_gost_screen(page)
    find_button(page, "20").on_click(None)
    find_item_container(page, "Ø20").on_click(None)

    dialog = page.dialogs[-1]
    quantity_field = next(
        control for control in walk(dialog)
        if isinstance(control, ft.TextField)
    )
    quantity_field.value = "1001"
    next(
        control for control in walk(dialog)
        if isinstance(control, ft.FilledButton) and text_of(control) == "Сохранить"
    ).on_click(None)

    # Dialog stays open and shows the inline error.
    assert page.dialogs[-1] is dialog
    errors = [
        control for control in walk(dialog)
        if isinstance(control, ft.Text)
        and "Введите целое число" in str(control.value)
    ]
    assert errors and errors[0].visible

    # 0 is allowed: the lower bound is inclusive.
    quantity_field.value = "0"
    next(
        control for control in walk(dialog)
        if isinstance(control, ft.FilledButton) and text_of(control) == "Сохранить"
    ).on_click(None)
    texts = [
        control.value for control in all_controls(page)
        if isinstance(control, ft.Text)
    ]
    assert "0 шт." in texts


def test_summary_shows_cost_for_each_item(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.sqlite3")
    page = FakePage()
    main(page)
    open_gost_screen(page)

    # Set a non-zero price for the 12-17 range.
    dialog = open_settings(page)
    price_fields = [
        control for control in walk(dialog)
        if isinstance(control, ft.TextField) and control.hint_text == "цена"
    ]
    price_fields[1].value = "2000"
    apply_settings(dialog)

    find_button(page, "14").on_click(None)
    find_button(page, "14").on_click(None)
    open_summary(page)

    volume = calculate_gost_item(14, Decimal(6), 1, load_gost_table()) * 2
    expected = f"{volume * Decimal(2000):.2f}"

    texts = [
        control.value for control in all_controls(page)
        if isinstance(control, ft.Text)
    ]
    # The item row itself shows money, not just the range subtotal.
    assert expected in texts
    # Subtotals still match the sum of item costs.
    assert texts.count(expected) == 2


def test_send_dialog_offers_download_and_share(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.sqlite3")
    page = FakePage()
    main(page)
    open_gost_screen(page)
    find_button(page, "14").on_click(None)
    open_summary(page)

    send_button = next(
        control for control in all_controls(page)
        if isinstance(control, ft.OutlinedButton)
        and text_of(control) == "Отправить"
    )
    send_button.on_click(None)

    dialog = page.dialogs[-1]
    assert isinstance(dialog, ft.AlertDialog)
    assert dialog.title.value == "Отправить расчёт"
    assert any(
        isinstance(control, ft.Text)
        and control.value == "расчет_1.xlsx"
        for control in walk(dialog)
    )
    assert any(
        isinstance(control, ft.FilledButton)
        and text_of(control) == "Поделиться"
        for control in walk(dialog)
    )
    assert any(
        isinstance(control, ft.OutlinedButton)
        and text_of(control) == "Скачать"
        for control in walk(dialog)
    )


def test_settings_single_range_and_counterparty_are_used_for_saving(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.sqlite3")
    storage.init_db()
    counterparty_id = storage.save_counterparty("ООО Лес", phone="+7 900")

    page = FakePage()
    main(page)
    open_gost_screen(page)
    dialog = open_settings(page)

    counterparty_dropdown = next(
        control for control in walk(dialog)
        if isinstance(control, ft.Dropdown)
        and control.label == "Контрагент"
    )
    counterparty_dropdown.value = str(counterparty_id)
    next(
        control for control in walk(dialog)
        if isinstance(control, ft.OutlinedButton)
        and text_of(control) == "Один диапазон"
    ).on_click(None)
    apply_settings(dialog)

    find_button(page, "14").on_click(None)
    open_summary(page)

    controls = list(all_controls(page))
    assert any(
        isinstance(control, ft.Text) and control.value == "[3-120]"
        for control in controls
    )
    assert any(
        isinstance(control, ft.Text)
        and "Контрагент: ООО Лес" in str(control.value)
        for control in controls
    )

    next(
        control for control in all_controls(page)
        if isinstance(control, ft.FilledButton)
        and text_of(control) == "Сохранить расчёт"
    ).on_click(None)
    party_dialog = page.dialogs[-1]
    assert isinstance(party_dialog, ft.AlertDialog)
    assert party_dialog.title.controls[1].value == "Новая партия"

    name_field = next(
        control for control in walk(party_dialog)
        if isinstance(control, ft.TextField) and control.label == "Название"
    )
    assert name_field.value.startswith("Кругляк ")
    date_part = name_field.value.removeprefix("Кругляк ")
    # День и месяц, например «26.11». На Android старый вариант с «%-d»
    # подставлял в название партии литерал «-d».
    day_part, month_part = date_part.split(".")
    assert day_part.isdigit() and len(day_part) <= 2
    assert month_part.isdigit() and len(month_part) == 2
    next(
        control for control in walk(party_dialog)
        if isinstance(control, ft.FilledButton)
        and text_of(control) == "Сохранить"
    ).on_click(None)

    parties = storage.list_parties()
    assert len(parties) == 1
    assert parties[0]["counterparty"]["name"] == "ООО Лес"
    assert parties[0]["payload"][0]["species"] == "н/д"
    assert parties[0]["payload"][0]["calc_type"] == "продажа"


def test_settings_show_standard_ranges_by_default(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.sqlite3")
    page = FakePage()
    main(page)
    open_gost_screen(page)
    dialog = open_settings(page)

    price_fields = [
        control for control in walk(dialog)
        if isinstance(control, ft.TextField) and control.hint_text == "цена"
    ]
    starts = [
        control for control in walk(dialog)
        if isinstance(control, ft.TextField) and control.hint_text == "от"
    ]
    ends = [
        control for control in walk(dialog)
        if isinstance(control, ft.TextField) and control.hint_text == "до"
    ]
    assert [field.value for field in starts] == ["3", "12", "18"]
    assert [field.value for field in ends] == ["11", "17", "120"]
    assert [field.value for field in price_fields] == ["0", "0", "0"]


class WebPage(FakePage):
    def __init__(self):
        super().__init__()
        self.web = True
        self.services = []


class FakeFilePicker:
    def __init__(self):
        self.saved = None

    async def save_file(self, **kwargs):
        self.saved = kwargs
        return kwargs.get("file_name")


def test_download_button_hands_xlsx_bytes_to_client(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr("main.DATA_DIR", tmp_path)

    pickers = []

    def make_picker():
        picker = FakeFilePicker()
        pickers.append(picker)
        return picker

    monkeypatch.setattr(ft, "FilePicker", make_picker)

    page = WebPage()
    main(page)
    open_gost_screen(page)
    find_button(page, "14").on_click(None)
    open_summary(page)

    download_button = next(
        control for control in all_controls(page)
        if isinstance(control, ft.OutlinedButton)
        and text_of(control) == "Скачать"
    )
    asyncio.run(download_button.on_click(None))

    assert len(pickers) == 1
    saved = pickers[0].saved
    assert saved["file_name"] == "расчет_1.xlsx"
    assert saved["file_type"] == ft.FilePickerFileType.CUSTOM
    assert saved["src_bytes"].startswith(b"PK")
    assert pickers[0] in page.services
    assert list(tmp_path.glob("*.xlsx")) == []


def test_xlsx_export_has_cost_for_each_item(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr("main.DATA_DIR", tmp_path)

    pickers = []

    def make_picker():
        picker = FakeFilePicker()
        pickers.append(picker)
        return picker

    monkeypatch.setattr(ft, "FilePicker", make_picker)

    page = WebPage()
    main(page)
    open_gost_screen(page)

    dialog = open_settings(page)
    price_fields = [
        control for control in walk(dialog)
        if isinstance(control, ft.TextField) and control.hint_text == "цена"
    ]
    price_fields[1].value = "2000"
    apply_settings(dialog)

    find_button(page, "14").on_click(None)
    open_summary(page)
    asyncio.run(next(
        control for control in all_controls(page)
        if isinstance(control, ft.OutlinedButton)
        and text_of(control) == "Скачать"
    ).on_click(None))

    sheet = load_workbook(BytesIO(pickers[0].saved["src_bytes"])).active
    item_row = next(
        row for row in range(1, sheet.max_row + 1)
        if sheet.cell(row=row, column=1).value == "14"
    )
    volume = float(calculate_gost_item(14, Decimal(6), 1, load_gost_table()))
    assert sheet.cell(row=item_row, column=5).value == pytest.approx(
        volume * 2000, rel=1e-6
    )


def test_settings_are_available_from_the_menu(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.sqlite3")
    page = FakePage()
    main(page)
    open_gost_screen(page)

    menu = next(
        action for action in page.appbar.actions
        if isinstance(action, ft.PopupMenuButton)
    )
    settings_item = next(
        item for item in menu.items
        if isinstance(item.content, ft.Text)
        and item.content.value == "Настройки расчёта"
    )
    settings_item.on_click(None)

    assert isinstance(page.dialogs[-1], ft.AlertDialog)
    assert page.dialogs[-1].title.value == "Настройки расчёта"


def test_settings_survive_saving_a_party(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.sqlite3")
    page = FakePage()
    main(page)
    open_gost_screen(page)
    dialog = open_settings(page)

    species = next(
        control for control in walk(dialog)
        if isinstance(control, ft.Dropdown) and control.label == "Порода"
    )
    species.value = "сосна"
    next(
        control for control in walk(dialog)
        if isinstance(control, ft.OutlinedButton)
        and text_of(control) == "Один диапазон"
    ).on_click(None)
    apply_settings(dialog)

    find_button(page, "14").on_click(None)
    open_summary(page)
    next(
        control for control in all_controls(page)
        if isinstance(control, ft.FilledButton)
        and text_of(control) == "Сохранить расчёт"
    ).on_click(None)
    next(
        control for control in walk(page.dialogs[-1])
        if isinstance(control, ft.FilledButton) and text_of(control) == "Сохранить"
    ).on_click(None)

    # The new calculation screen must keep the settings after the draft reset.
    second = FakePage()
    main(second)
    open_gost_screen(second)
    dialog = open_settings(second)
    species = next(
        control for control in walk(dialog)
        if isinstance(control, ft.Dropdown) and control.label == "Порода"
    )
    assert species.value == "сосна"
    starts = [
        control for control in walk(dialog)
        if isinstance(control, ft.TextField) and control.hint_text == "от"
    ]
    assert [field.value for field in starts] == ["3"]


def test_xlsx_export_includes_counterparty_contacts():
    data = build_calculation_xlsx({
        "number": 5,
        "title": "Расчет #5",
        "date": "26.11.2026",
        "species": "сосна",
        "calc_type": "продажа",
        "counterparty": "ООО Лес",
        "counterparty_phone": "+7 900 000-00-00",
        "counterparty_email": "les@example.ru",
        "price_text": "1000.0 RUB.",
        "rows": [],
        "total_quantity": 0,
        "total_volume": 0,
        "total_cost": 0,
    })

    sheet = load_workbook(BytesIO(data)).active
    metadata = {
        sheet.cell(row=row, column=1).value: sheet.cell(row=row, column=2).value
        for row in range(2, 10)
    }
    assert metadata["Контрагент:"] == "ООО Лес"
    assert metadata["Телефон:"] == "+7 900 000-00-00"
    assert metadata["Email:"] == "les@example.ru"
    # Contacts push the table header down one row per extra field.
    assert sheet["A10"].value == "Диаметр"


def test_xlsx_export_contains_grouped_rows_and_totals():
    data = build_calculation_xlsx({
        "number": 4,
        "title": "Расчет #4 (ГОСТ-75-Табл.1)",
        "date": "26.11.2026",
        "species": "сосна",
        "calc_type": "продажа",
        "counterparty": "ООО Лес",
        "price_text": "2000.0 RUB.",
        "rows": [
            {"label": "14", "length": "6.0", "quantity": 1,
             "volume": 0.123, "cost": None, "bold": False},
            {"label": "[12-17]", "length": "", "quantity": 1,
             "volume": 0.123, "cost": 246.0, "bold": True},
        ],
        "total_quantity": 1,
        "total_volume": 0.123,
        "total_cost": 246.0,
    })

    workbook = load_workbook(BytesIO(data))
    sheet = workbook.active
    assert sheet["A1"].value == "Расчет #4 (ГОСТ-75-Табл.1)"
    assert sheet["A8"].value == "Диаметр"
    assert sheet["A9"].value == "14"
    assert sheet["E9"].value == "-"
    assert sheet["A10"].value == "[12-17]"
    assert sheet["E10"].value == 246.0
    assert sheet["A11"].value == "Итого"
    assert sheet["E11"].value == 246.0
