"""Smoke tests for the calculator screen using Flet controls."""

import flet as ft

from app import storage
from main import main


class FakePage:
    def __init__(self):
        self.controls = []
        self.snack_bar = None
        self.title = None
        self.appbar = None
        self.dialogs = []

    def add(self, *controls):
        self.controls.extend(controls)

    def update(self):
        pass

    def show_dialog(self, dialog):
        self.dialogs.append(dialog)

    def pop_dialog(self):
        if self.dialogs:
            self.dialogs.pop()


def walk(control):
    if control is None:
        return
    yield control
    for child in getattr(control, "controls", []) or []:
        yield from walk(child)
    content = getattr(control, "content", None)
    if content is not None and not isinstance(content, str):
        yield from walk(content)
    for name in ("leading", "trailing", "title", "subtitle"):
        child = getattr(control, name, None)
        if child is not None and not isinstance(child, str):
            yield from walk(child)
    for child in getattr(control, "actions", []) or []:
        yield from walk(child)


def all_controls(page):
    for control in page.controls:
        yield from walk(control)


def text_of(control):
    content = getattr(control, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, ft.Text):
        return content.value
    if isinstance(content, ft.Row):
        return " ".join(
            child.value for child in content.controls if isinstance(child, ft.Text)
        )
    return ""


def test_home_screen_builds_with_installed_flet_api(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.sqlite3")
    page = FakePage()

    main(page)

    assert page.title == "Кубатура Экспресс"
    assert isinstance(page.appbar, ft.AppBar)
    assert any(
        isinstance(control, ft.ListTile)
        and isinstance(control.title, ft.Text)
        and control.title.value == "ГОСТ 2708-75 · Таблица 1"
        for control in all_controls(page)
    )


def test_diameter_tap_adds_log_and_save_button_is_available(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.sqlite3")
    page = FakePage()
    main(page)

    gost_tile = next(
        control
        for control in all_controls(page)
        if isinstance(control, ft.ListTile)
        and isinstance(control.title, ft.Text)
        and control.title.value == "ГОСТ 2708-75 · Таблица 1"
    )
    gost_tile.on_click(None)

    length_button = next(
        control
        for control in all_controls(page)
        if isinstance(control, ft.FilledButton) and "ДЛИНА:" in text_of(control)
    )
    assert length_button is not None

    diameter_button = next(
        control
        for control in all_controls(page)
        if isinstance(control, ft.FilledButton) and text_of(control) == "20"
    )
    diameter_button.on_click(None)

    assert any(
        isinstance(control, ft.Text) and "Ø20" in str(control.value)
        for control in all_controls(page)
    )
    assert any(
        isinstance(control, ft.Text) and "6.0 м" in str(control.value)
        for control in all_controls(page)
    )

    save_button = next(
        control
        for control in all_controls(page)
        if isinstance(control, ft.FilledButton) and "Сохранить" in text_of(control)
    )

    assert save_button.disabled is False
    assert storage.list_calculations() == []


def open_gost_screen(page):
    gost_tile = next(
        control
        for control in all_controls(page)
        if isinstance(control, ft.ListTile)
        and isinstance(control.title, ft.Text)
        and control.title.value == "ГОСТ 2708-75 · Таблица 1"
    )
    gost_tile.on_click(None)


def find_button(page, text):
    return next(
        control
        for control in all_controls(page)
        if isinstance(control, ft.FilledButton) and text_of(control) == text
    )


def test_gost_volume_comes_from_table(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.sqlite3")
    page = FakePage()
    main(page)
    open_gost_screen(page)

    find_button(page, "20").on_click(None)

    assert any(
        isinstance(control, ft.Text) and control.value == "0.2300 м³"
        for control in all_controls(page)
    )


def test_gost_missing_value_shows_close_dialog(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.sqlite3")
    page = FakePage()
    main(page)
    open_gost_screen(page)

    find_button(page, "ДЛИНА: 6").on_click(None)
    length_dialog = page.dialogs[-1]
    length_input = next(
        control
        for control in walk(length_dialog)
        if isinstance(control, ft.TextField)
    )
    length_input.value = "6.33"
    next(
        control
        for control in walk(length_dialog)
        if isinstance(control, ft.FilledButton) and text_of(control) == "Применить"
    ).on_click(None)

    find_button(page, "20").on_click(None)

    dialog = page.dialogs[-1]
    assert isinstance(dialog, ft.AlertDialog)
    assert isinstance(dialog.title, ft.Text)
    assert dialog.title.value == "Нет значения в таблице"
    assert any(
        isinstance(control, ft.FilledButton) and text_of(control) == "Закрыть"
        for control in walk(dialog)
    )
