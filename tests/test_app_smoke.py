"""Headless smoke tests: instantiate the real Flet controls and exercise core flows."""

import flet as ft

from app import storage
from main import main


class FakePage:
    """Small Page stand-in; real Flet controls are still constructed."""

    def __init__(self):
        self.controls = []
        self.snack_bar = None

    def add(self, *controls):
        self.controls.extend(controls)

    def update(self):
        pass


def walk(control):
    """Yield a control and all nested controls without depending on layout type."""
    if control is None:
        return
    yield control
    for attr in ("controls",):
        children = getattr(control, attr, None)
        if children:
            for child in children:
                yield from walk(child)
    content = getattr(control, "content", None)
    if content is not None:
        yield from walk(content)
    for attr in ("leading", "trailing", "title", "subtitle"):
        child = getattr(control, attr, None)
        if child is not None and not isinstance(child, str):
            yield from walk(child)


def all_controls(page):
    for root in page.controls:
        yield from walk(root)


def test_home_screen_builds_with_installed_flet_api(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.sqlite3")
    page = FakePage()

    main(page)

    assert page.title == "Расчёт кубатуры"
    assert isinstance(page.appbar, ft.AppBar)
    assert any(
        isinstance(c, ft.Text) and c.value == "ГОСТ 2708-75 · Таблица 1"
        for c in all_controls(page)
    )


def test_gost_screen_adds_and_saves_item(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.sqlite3")
    page = FakePage()
    main(page)

    gost_tile = next(
        c for c in all_controls(page)
        if isinstance(c, ft.ListTile)
        and isinstance(c.title, ft.Text)
        and c.title.value == "ГОСТ 2708-75 · Таблица 1"
    )
    gost_tile.on_click(None)

    fields = [c for c in all_controls(page) if isinstance(c, ft.TextField)]
    assert len(fields) == 3
    fields[0].value = "20"
    fields[1].value = "6.0"
    fields[2].value = "2"

    add_button = next(
        c for c in all_controls(page)
        if isinstance(c, ft.FilledButton)
        and isinstance(c.content, ft.Text)
        and c.content.value == "Добавить"
    )
    add_button.on_click(None)

    assert any(
        isinstance(c, ft.Text) and "Ø20 · 6.0 м × 2 шт." in str(c.value)
        for c in all_controls(page)
    )

    save_button = next(
        c for c in all_controls(page)
        if isinstance(c, ft.FilledButton)
        and isinstance(c.content, ft.Text)
        and c.content.value == "Сохранить расчёт"
    )
    save_button.on_click(None)

    assert storage.list_calculations()[0]["items_count"] == 1
    assert (tmp_path / "test.sqlite3").exists()
