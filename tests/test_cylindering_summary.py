"""Оцилиндровка reuses the shared «Итоги» screen."""

from decimal import ROUND_HALF_UP, Decimal

import flet as ft
from test_app_smoke import FakePage, all_controls, text_of, walk

from app import storage
from app.cylindering import cylinder_volume
from main import main


def open_cylindering(page):
    tile = next(
        control for control in all_controls(page)
        if isinstance(control, ft.ListTile)
        and isinstance(control.title, ft.Text)
        and "Оцилиндровка" in control.title.value
    )
    tile.on_click(None)


def open_summary(page):
    next(
        control for control in all_controls(page)
        if isinstance(control, ft.TextButton) and text_of(control) == "Итоги"
    ).on_click(None)


def find_button(page, text):
    return next(
        control for control in all_controls(page)
        if isinstance(control, ft.FilledButton) and text_of(control) == text
    )


def test_cylindering_summary_matches_gost_actions(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.sqlite3")
    page = FakePage()
    main(page)
    open_cylindering(page)
    find_button(page, "20").on_click(None)
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


def test_cylindering_info_dialog_reports_details(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.sqlite3")
    page = FakePage()
    main(page)
    open_cylindering(page)
    find_button(page, "20").on_click(None)
    find_button(page, "24").on_click(None)
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
    assert "2 шт." in texts
    assert "24 см" in texts
    assert "20 см" in texts
    assert "22.0 см" in texts


def test_cylindering_save_creates_party(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.sqlite3")
    page = FakePage()
    main(page)
    open_cylindering(page)
    find_button(page, "20").on_click(None)
    open_summary(page)

    next(
        control for control in all_controls(page)
        if isinstance(control, ft.FilledButton)
        and text_of(control) == "Сохранить расчёт"
    ).on_click(None)

    dialog = page.dialogs[-1]
    assert isinstance(dialog, ft.AlertDialog)
    next(
        control for control in walk(dialog)
        if isinstance(control, ft.FilledButton) and text_of(control) == "Сохранить"
    ).on_click(None)

    parties = storage.list_parties()
    assert len(parties) == 1
    assert parties[0]["type"] == "Оцилиндровка"
    assert parties[0]["payload"][0]["diameter_cm"] == 20


def test_cylindering_summary_shows_cost_for_each_item(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.sqlite3")
    page = FakePage()
    main(page)
    open_cylindering(page)

    next(
        control for control in all_controls(page)
        if isinstance(control, ft.IconButton)
        and control.tooltip == "Настройки расчёта"
    ).on_click(None)
    dialog = page.dialogs[-1]
    price_fields = [
        control for control in walk(dialog)
        if isinstance(control, ft.TextField) and control.hint_text == "цена"
    ]
    price_fields[2].value = "2000"
    next(
        control for control in walk(dialog)
        if isinstance(control, ft.FilledButton) and text_of(control) == "Применить"
    ).on_click(None)

    find_button(page, "20").on_click(None)
    open_summary(page)

    # Items keep volumes rounded to the screen rounding (3 digits by default).
    volume = Decimal(str(cylinder_volume(20, 7, 1))).quantize(
        Decimal("0.001"), rounding=ROUND_HALF_UP
    )
    expected = f"{volume * Decimal(2000):.2f}"
    texts = [
        control.value for control in all_controls(page)
        if isinstance(control, ft.Text)
    ]
    assert expected in texts
    assert texts.count(expected) == 2


def test_cylindering_clear_resets_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.sqlite3")
    page = FakePage()
    main(page)
    open_cylindering(page)
    find_button(page, "20").on_click(None)

    settings_button = next(
        control for control in all_controls(page)
        if isinstance(control, ft.IconButton)
        and control.tooltip == "Настройки расчёта"
    )
    settings_button.on_click(None)
    dialog = page.dialogs[-1]
    filter_dropdown = next(
        control for control in walk(dialog)
        if isinstance(control, ft.Dropdown)
        and control.label == "Показ диаметров"
    )
    filter_dropdown.value = "odd"
    next(
        control for control in walk(dialog)
        if isinstance(control, ft.FilledButton) and text_of(control) == "Применить"
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

    settings_button = next(
        control for control in all_controls(page)
        if isinstance(control, ft.IconButton)
        and control.tooltip == "Настройки расчёта"
    )
    settings_button.on_click(None)
    dialog = page.dialogs[-1]
    filter_dropdown = next(
        control for control in walk(dialog)
        if isinstance(control, ft.Dropdown)
        and control.label == "Показ диаметров"
    )
    assert filter_dropdown.value == "all"
    starts = [
        control for control in walk(dialog)
        if isinstance(control, ft.TextField) and control.hint_text == "от"
    ]
    assert [field.value for field in starts] == ["3", "12", "18"]
    assert not any(
        isinstance(control, ft.Text) and str(control.value).startswith("Ø20")
        for control in all_controls(page)
    )


def test_cylindering_delete_records_keeps_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.sqlite3")
    page = FakePage()
    main(page)
    open_cylindering(page)
    find_button(page, "20").on_click(None)

    settings_button = next(
        control for control in all_controls(page)
        if isinstance(control, ft.IconButton)
        and control.tooltip == "Настройки расчёта"
    )
    settings_button.on_click(None)
    dialog = page.dialogs[-1]
    next(
        control for control in walk(dialog)
        if isinstance(control, ft.OutlinedButton)
        and text_of(control) == "Один диапазон"
    ).on_click(None)
    next(
        control for control in walk(dialog)
        if isinstance(control, ft.FilledButton) and text_of(control) == "Применить"
    ).on_click(None)

    menu = next(
        action for action in page.appbar.actions
        if isinstance(action, ft.PopupMenuButton)
    )
    items = [
        item.content.value for item in menu.items
        if isinstance(item.content, ft.Text)
    ]
    assert items.index("Удалить записи") < items.index("Очистить расчёт")

    next(
        item for item in menu.items
        if isinstance(item.content, ft.Text)
        and item.content.value == "Удалить записи"
    ).on_click(None)
    confirm = page.dialogs[-1]
    assert confirm.title.value == "Удалить записи?"
    next(
        control for control in walk(confirm)
        if isinstance(control, ft.TextButton) and text_of(control) == "Удалить"
    ).on_click(None)

    assert not any(
        isinstance(control, ft.Text) and str(control.value).startswith("Ø20")
        for control in all_controls(page)
    )
    settings_button = next(
        control for control in all_controls(page)
        if isinstance(control, ft.IconButton)
        and control.tooltip == "Настройки расчёта"
    )
    settings_button.on_click(None)
    dialog = page.dialogs[-1]
    starts = [
        control for control in walk(dialog)
        if isinstance(control, ft.TextField) and control.hint_text == "от"
    ]
    assert [field.value for field in starts] == ["3"]


def test_cylindering_summary_splits_groups_by_length(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.sqlite3")
    page = FakePage()
    main(page)
    open_cylindering(page)
    find_button(page, "20").on_click(None)

    # Change length from the default 7 to 4 and add another log.
    next(
        control for control in all_controls(page)
        if isinstance(control, ft.FilledButton)
        and "ДЛИНА:" in text_of(control)
    ).on_click(None)
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
    assert len(groups) == 2


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


def test_cylindering_same_logs_merge_and_row_opens_quantity(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.sqlite3")
    page = FakePage()
    main(page)
    open_cylindering(page)

    find_button(page, "20").on_click(None)
    find_button(page, "20").on_click(None)

    texts = [
        control.value for control in all_controls(page)
        if isinstance(control, ft.Text)
    ]
    assert texts.count("Ø20") == 1
    assert "2 шт." in texts

    find_item_container(page, "Ø20").on_click(None)

    dialog = page.dialogs[-1]
    assert dialog.title.value == "Выберите количество Ø20 7м"
    quantity_field = next(
        control for control in walk(dialog)
        if isinstance(control, ft.TextField)
    )
    assert quantity_field.autofocus is True
    assert quantity_field.keyboard_type == ft.KeyboardType.NUMBER
    quantity_field.value = "5"
    next(
        control for control in walk(dialog)
        if isinstance(control, ft.FilledButton) and text_of(control) == "Сохранить"
    ).on_click(None)

    texts = [
        control.value for control in all_controls(page)
        if isinstance(control, ft.Text)
    ]
    assert "5 шт." in texts


def test_cylindering_settings_filter_diameters(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.sqlite3")
    page = FakePage()
    main(page)
    open_cylindering(page)

    settings_button = next(
        control for control in all_controls(page)
        if isinstance(control, ft.IconButton)
        and control.tooltip == "Настройки расчёта"
    )
    settings_button.on_click(None)
    dialog = page.dialogs[-1]
    assert dialog.title.value == "Настройки расчёта"

    filter_dropdown = next(
        control for control in walk(dialog)
        if isinstance(control, ft.Dropdown)
        and control.label == "Показ диаметров"
    )
    filter_dropdown.value = "even"
    next(
        control for control in walk(dialog)
        if isinstance(control, ft.FilledButton) and text_of(control) == "Применить"
    ).on_click(None)

    assert not any(
        isinstance(control, ft.FilledButton) and text_of(control) == "5"
        for control in all_controls(page)
    )
    assert any(
        isinstance(control, ft.FilledButton) and text_of(control) == "6"
        for control in all_controls(page)
    )
