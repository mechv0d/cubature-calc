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

    assert page.title == "Расчёт кубатуры"
    assert isinstance(page.appbar, ft.AppBar)
    assert any(
        isinstance(control, ft.ListTile)
        and isinstance(control.title, ft.Text)
        and control.title.value == "ГОСТ 2708-75 · Таблица 1"
        for control in all_controls(page)
    )


def test_diameter_tap_adds_log_with_selected_length_and_saves(tmp_path, monkeypatch):
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
    save_button.on_click(None)

    calculations = storage.list_calculations()
    assert len(calculations) == 1
    assert calculations[0]["items_count"] == 1
    assert (tmp_path / "test.sqlite3").exists()