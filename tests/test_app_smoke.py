"""Headless smoke tests for the Flet application."""

import flet as ft

from app import storage
from main import main


class FakePage:
    """Minimal Page stand-in for headless tests."""

    def __init__(self):
        self.controls = []
        self.snack_bar = None
        self.title = None
        self.appbar = None

    def add(self, *controls):
        self.controls.extend(controls)

    def update(self):
        pass


def walk(control):
    """Recursively yield controls nested inside layouts and containers."""
    if control is None:
        return

    yield control

    children = getattr(control, "controls", None)
    if children:
        for child in children:
            yield from walk(child)

    content = getattr(control, "content", None)
    if content is not None and not isinstance(content, str):
        yield from walk(content)

    for attr in ("leading", "trailing", "title", "subtitle"):
        child = getattr(control, attr, None)
        if child is not None and not isinstance(child, str):
            yield from walk(child)


def all_controls(page):
    for root in page.controls:
        yield from walk(root)


def button_text(button):
    """Get button label across supported Flet content representations."""
    content = button.content

    if isinstance(content, ft.Text):
        return content.value

    if isinstance(content, str):
        return content

    return None


def find_button(page, label):
    return next(
        control
        for control in all_controls(page)
        if isinstance(control, ft.FilledButton)
        and button_text(control) == label
    )


def test_home_screen_builds_with_installed_flet_api(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        storage, "DB_PATH", tmp_path / "test.sqlite3"
    )

    page = FakePage()
    main(page)

    assert page.title == "Расчёт кубатуры"
    assert isinstance(page.appbar, ft.AppBar)

    assert any(
        isinstance(control, ft.Text)
        and control.value == "ГОСТ 2708-75 · Таблица 1"
        for control in all_controls(page)
    )


def test_gost_screen_adds_and_saves_item(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        storage, "DB_PATH", tmp_path / "test.sqlite3"
    )

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

    fields = [
        control
        for control in all_controls(page)
        if isinstance(control, ft.TextField)
    ]

    assert len(fields) == 3

    fields[0].value = "20"
    fields[1].value = "6.0"
    fields[2].value = "2"

    add_button = find_button(page, "Добавить")
    add_button.on_click(None)

    assert any(
        isinstance(control, ft.Text)
        and "Ø20 · 6.0 м × 2 шт." in str(control.value)
        for control in all_controls(page)
    )

    save_button = find_button(page, "Сохранить расчёт")
    save_button.on_click(None)

    calculations = storage.list_calculations()

    assert len(calculations) == 1
    assert calculations[0]["items_count"] == 1
    assert (tmp_path / "test.sqlite3").exists()
