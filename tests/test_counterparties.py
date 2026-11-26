"""Counterparty registry: validation, management screen and party dialog."""

from types import SimpleNamespace

import flet as ft
import pytest
from test_app_smoke import (
    FakePage,
    all_controls,
    find_button,
    open_gost_screen,
    text_of,
    walk,
)

from app import storage
from main import main


def find_by_text(controls, text, cls=ft.FilledButton):
    return next(
        control
        for control in controls
        if isinstance(control, cls) and text_of(control) == text
    )


def open_parties_screen(page):
    page.navigation_bar.on_change(
        SimpleNamespace(control=SimpleNamespace(selected_index=1))
    )


def test_counterparty_name_is_required_and_repeat_save_updates_fields(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.sqlite3")
    storage.init_db()

    counterparty_id = storage.save_counterparty("ООО Ромашка", phone="+7 900")
    assert [cp["name"] for cp in storage.list_counterparties()] == ["ООО Ромашка"]

    with pytest.raises(ValueError):
        storage.save_counterparty("  ")

    # Saving the same name again updates the other fields instead of failing.
    repeated_id = storage.save_counterparty(
        "ооо ромашка", phone="+7 901", email="mail@example.com", info="склад",
    )
    assert repeated_id == counterparty_id
    counterparties = storage.list_counterparties()
    assert len(counterparties) == 1
    assert counterparties[0]["name"] == "ООО Ромашка"
    assert counterparties[0]["phone"] == "+7 901"
    assert counterparties[0]["email"] == "mail@example.com"
    assert counterparties[0]["info"] == "склад"

    storage.update_counterparty(counterparty_id, "ООО Лютик")
    assert storage.list_counterparties()[0]["name"] == "ООО Лютик"
    with pytest.raises(ValueError):
        storage.update_counterparty(counterparty_id, "")

    storage.delete_counterparty(counterparty_id)
    assert storage.list_counterparties() == []


def test_parties_screen_has_counterparties_button_and_add_dialog(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.sqlite3")
    page = FakePage()
    main(page)
    open_parties_screen(page)

    find_by_text(all_controls(page), "Контрагенты").on_click(None)

    find_by_text(all_controls(page), "Добавить контрагента").on_click(None)
    dialog = page.dialogs[-1]
    name = next(
        control for control in walk(dialog)
        if isinstance(control, ft.TextField) and control.label == "Название"
    )
    name.value = "ИП Петров"
    find_by_text(walk(dialog), "Сохранить").on_click(None)

    assert [cp["name"] for cp in storage.list_counterparties()] == ["ИП Петров"]
    assert any(
        isinstance(control, ft.Text) and control.value == "ИП Петров"
        for control in all_controls(page)
    )


def test_create_party_dialog_saves_and_uses_counterparty(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.sqlite3")
    page = FakePage()
    main(page)
    open_gost_screen(page)
    find_button(page, "20").on_click(None)
    find_button(page, "Сохранить").on_click(None)

    dialog = page.dialogs[-1]
    name = next(
        control for control in walk(dialog)
        if isinstance(control, ft.TextField)
        and control.label == "Название контрагента"
    )
    name.value = "ООО Тест"
    find_by_text(walk(dialog), "Сохранить контрагента", ft.OutlinedButton).on_click(None)

    assert [cp["name"] for cp in storage.list_counterparties()] == ["ООО Тест"]

    find_by_text(walk(dialog), "Сохранить").on_click(None)

    parties = storage.list_parties()
    assert len(parties) == 1
    assert parties[0]["counterparty"]["name"] == "ООО Тест"


def test_party_dialog_repeat_save_updates_counterparty_fields(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.sqlite3")
    storage.init_db()
    storage.save_counterparty("ООО Тест", phone="+7 900")

    page = FakePage()
    main(page)
    open_gost_screen(page)
    find_button(page, "20").on_click(None)
    find_button(page, "Сохранить").on_click(None)

    dialog = page.dialogs[-1]
    fields = {
        control.label: control for control in walk(dialog)
        if isinstance(control, ft.TextField)
    }
    fields["Название контрагента"].value = "ооо тест"
    fields["Телефон"].value = "+7 901"
    fields["Email"].value = "new@example.com"
    find_by_text(walk(dialog), "Сохранить контрагента", ft.OutlinedButton).on_click(None)

    counterparties = storage.list_counterparties()
    assert len(counterparties) == 1
    assert counterparties[0]["phone"] == "+7 901"
    assert counterparties[0]["email"] == "new@example.com"
    assert any(
        isinstance(control, ft.Text) and control.value == "Контрагент обновлён"
        for control in walk(dialog)
    )
