"""Lumber editor: quantity focus and first-input replacement."""

from types import SimpleNamespace

import flet as ft
from test_app_smoke import (
    FakePage,
    all_controls,
    find_button,
    text_of,
    walk,
)

from app import storage
from main import main


def open_lumber_screen(page):
    tile = next(
        control
        for control in all_controls(page)
        if isinstance(control, ft.ListTile)
        and isinstance(control.title, ft.Text)
        and control.title.value == "Пиломатериалы"
    )
    tile.on_click(None)


def find_clickable_with_text(page, text):
    for control in all_controls(page):
        if isinstance(control, ft.Container) and control.on_click is not None:
            texts = [
                child.value for child in walk(control)
                if isinstance(child, ft.Text)
            ]
            if text in texts:
                return control
    raise AssertionError(f"clickable {text} not found")


def editor_fields(dialog):
    return [
        control for control in walk(dialog)
        if isinstance(control, ft.TextField)
    ]


def fill_dimensions(fields, thickness="5", width="10", length="2"):
    # Field order: thickness, width, length, quantity, price.
    fields[0].value = thickness
    fields[1].value = width
    fields[2].value = length


def save_editor(dialog):
    next(
        control for control in walk(dialog)
        if isinstance(control, ft.FilledButton) and text_of(control) == "OK"
    ).on_click(None)


def test_new_lumber_starts_on_thickness_with_value_selected(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.sqlite3")
    page = FakePage()
    main(page)
    open_lumber_screen(page)

    find_button(page, "Добавить").on_click(None)
    dialog = page.dialogs[-1]
    fields = editor_fields(dialog)
    # Field order: thickness, width, length, quantity, price.
    thickness = fields[0]
    assert thickness.autofocus is True
    assert thickness.value == "0"
    selection = thickness.selection
    assert isinstance(selection, ft.TextSelection)
    assert (selection.base_offset, selection.extent_offset) == (0, 1)

    # First typed digit replaces the placeholder "0" ("05" -> "5").
    thickness.on_focus(SimpleNamespace(control=thickness))
    thickness.value = "5"
    thickness.on_change(SimpleNamespace(control=thickness))
    selection = thickness.selection
    assert (selection.base_offset, selection.extent_offset) == (1, 1)

    # The field is touched: focusing again does not select the value.
    thickness.on_focus(SimpleNamespace(control=thickness))
    selection = thickness.selection
    assert (selection.base_offset, selection.extent_offset) == (1, 1)


def test_ok_button_is_centered_below_the_fields(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.sqlite3")
    page = FakePage()
    main(page)
    open_lumber_screen(page)

    find_button(page, "Добавить").on_click(None)
    dialog = page.dialogs[-1]
    ok_button = next(
        control for control in walk(dialog)
        if isinstance(control, ft.FilledButton) and text_of(control) == "OK"
    )
    ok_row = next(
        control for control in walk(dialog)
        if isinstance(control, ft.Row)
        and any(child is ok_button for child in control.controls)
    )
    assert ok_row.alignment == ft.MainAxisAlignment.CENTER
    assert ok_button.width == 160


def test_new_lumber_quantity_replaces_default_one_on_first_input(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.sqlite3")
    page = FakePage()
    main(page)
    open_lumber_screen(page)

    find_button(page, "Добавить").on_click(None)
    dialog = page.dialogs[-1]
    fields = editor_fields(dialog)
    quantity = next(field for field in fields if field.value == "1")

    # The default "1" is selected as soon as the quantity field is focused.
    quantity.on_focus(SimpleNamespace(control=quantity))
    selection = quantity.selection
    assert isinstance(selection, ft.TextSelection)
    assert (selection.base_offset, selection.extent_offset) == (0, 1)

    # First typed digit replaces "1" and the field becomes "touched".
    quantity.value = "5"
    quantity.on_change(SimpleNamespace(control=quantity))
    selection = quantity.selection
    assert (selection.base_offset, selection.extent_offset) == (1, 1)

    # Further digits append: the field is no longer auto-selected.
    quantity.on_focus(SimpleNamespace(control=quantity))
    selection = quantity.selection
    assert (selection.base_offset, selection.extent_offset) == (1, 1)
    quantity.value = "52"
    quantity.on_change(SimpleNamespace(control=quantity))

    fill_dimensions(fields)
    save_editor(dialog)

    texts = [
        control.value for control in all_controls(page)
        if isinstance(control, ft.Text)
    ]
    assert "52 шт." in texts


def test_tapping_lumber_quantity_focuses_the_field(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.sqlite3")
    page = FakePage()
    main(page)
    open_lumber_screen(page)

    # Create one position to edit afterwards.
    find_button(page, "Добавить").on_click(None)
    dialog = page.dialogs[-1]
    fields = editor_fields(dialog)
    fields[3].value = "5"
    fill_dimensions(fields)
    save_editor(dialog)

    find_clickable_with_text(page, "5 шт.").on_click(None)

    dialog = page.dialogs[-1]
    fields = editor_fields(dialog)
    # Field order: thickness, width, length, quantity, price.
    quantity = fields[3]
    assert quantity.value == "5"
    # The quantity field gets focus (keyboard opens) but existing values are
    # not auto-selected.
    assert quantity.autofocus is True
    assert quantity.selection is None

    quantity.value = "7"
    save_editor(dialog)

    texts = [
        control.value for control in all_controls(page)
        if isinstance(control, ft.Text)
    ]
    assert "7 шт." in texts
