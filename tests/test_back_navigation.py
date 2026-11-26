"""Системная кнопка «Назад»: возврат по экранам и выход из приложения."""

import asyncio
from types import SimpleNamespace

import flet as ft
from test_app_smoke import (
    FakePage,
    all_controls,
    find_button,
    open_gost_screen,
    text_of,
    walk,
)

from app import navigation, storage
from app.navigation import get_navigator
from main import main


def back(page):
    asyncio.run(get_navigator(page).handle_back())


def texts(page):
    return [
        control.value for control in all_controls(page)
        if isinstance(control, ft.Text)
    ]


def open_cylindering(page):
    next(
        control for control in all_controls(page)
        if isinstance(control, ft.ListTile)
        and isinstance(control.title, ft.Text)
        and "Оцилиндровка" in control.title.value
    ).on_click(None)


def open_parties(page):
    page.navigation_bar.on_change(
        SimpleNamespace(control=SimpleNamespace(selected_index=1))
    )


def open_reference(page):
    page.navigation_bar.on_change(
        SimpleNamespace(control=SimpleNamespace(selected_index=2))
    )


def open_article(page, title):
    next(
        control for control in all_controls(page)
        if isinstance(control, ft.Container)
        and control.on_click is not None
        and any(
            isinstance(child, ft.Text) and child.value == title
            for child in walk(control)
        )
    ).on_click(None)


def open_party_card(page, name):
    next(
        control for control in all_controls(page)
        if isinstance(control, ft.Container)
        and control.on_click is not None
        and any(
            isinstance(child, ft.Text) and child.value == name
            for child in walk(control)
        )
    ).on_click(None)


def open_summary(page):
    next(
        control for control in all_controls(page)
        if isinstance(control, ft.TextButton) and text_of(control) == "Итоги"
    ).on_click(None)


def make_page(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.sqlite3")
    page = FakePage()
    main(page)
    return page


class FakeView:
    """Заглушка ``ft.View`` для проверки перехвата системного «Назад»."""

    def __init__(self):
        self.can_pop = True
        self.on_confirm_pop = None
        self.confirmations = []

    async def confirm_pop(self, should_pop):
        self.confirmations.append(should_pop)


def test_attach_intercepts_system_back(tmp_path, monkeypatch):
    page = make_page(tmp_path, monkeypatch)
    page.views = [FakeView()]
    navigator = navigation.Navigator(page)
    navigator.attach()

    assert page.views[0].can_pop is False
    assert page.views[0].on_confirm_pop == navigator.handle_back

    navigator.reset("/", lambda: None)
    back(page)
    # The first press only warns: the view must stay.
    assert page.views[0].confirmations == [False]
    back(page)
    # The second press allows the app to close.
    assert page.views[0].confirmations[-1] is True


def test_global_back_helper_prefers_the_real_dialog_stack():
    class Dialogs:
        def __init__(self):
            self.controls = []

    class Page:
        def __init__(self):
            self._dialogs = Dialogs()
            self.dialogs = []

    page = Page()
    dialog = ft.AlertDialog(modal=True, title=ft.Text("Вопрос"))
    dialog.open = True
    page._dialogs.controls.append(dialog)
    assert navigation.open_dialogs(page) == [dialog]

    dialog.open = False
    assert navigation.open_dialogs(page) == []


def test_back_from_summary_returns_to_calculation_table(tmp_path, monkeypatch):
    page = make_page(tmp_path, monkeypatch)
    open_gost_screen(page)
    find_button(page, "20").on_click(None)
    open_summary(page)
    assert "Сводная таблица:" in texts(page)

    back(page)

    assert "Сводная таблица:" not in texts(page)
    # The calculation is not lost and the screen is still the ГОСТ one.
    assert any("Ø20" in str(text) for text in texts(page))
    assert get_navigator(page).route == "/gost"


def test_back_from_gost_calculator_returns_home(tmp_path, monkeypatch):
    page = make_page(tmp_path, monkeypatch)
    open_gost_screen(page)

    back(page)

    assert page.appbar.title.value.startswith("Кубатура Экспресс")
    assert get_navigator(page).is_root


def test_back_from_lumber_and_cylindering_returns_home(tmp_path, monkeypatch):
    page = make_page(tmp_path, monkeypatch)
    next(
        control for control in all_controls(page)
        if isinstance(control, ft.ListTile)
        and isinstance(control.title, ft.Text)
        and control.title.value == "Пиломатериалы"
    ).on_click(None)
    back(page)
    assert page.appbar.title.value.startswith("Кубатура Экспресс")

    open_cylindering(page)
    assert get_navigator(page).route == "/cylindering"
    back(page)
    assert page.appbar.title.value.startswith("Кубатура Экспресс")


def test_back_at_main_screen_warns_and_exits_on_second_press(
    tmp_path, monkeypatch
):
    page = make_page(tmp_path, monkeypatch)
    open_parties(page)
    assert page.appbar.title.value == "Партии"

    back(page)
    # The warning is shown and the screen stays.
    warnings = [
        dialog for dialog in page.dialogs
        if isinstance(dialog, ft.SnackBar)
        and navigation.EXIT_WARNING in str(dialog.content.value)
    ]
    assert warnings
    assert page.appbar.title.value == "Партии"
    assert not get_navigator(page).exit_requested

    back(page)
    assert get_navigator(page).exit_requested


def test_exit_requires_presses_within_the_time_window(tmp_path, monkeypatch):
    page = make_page(tmp_path, monkeypatch)
    # A negative window means the first press has already expired.
    monkeypatch.setattr(navigation, "EXIT_WINDOW_SECONDS", -1)

    back(page)
    back(page)

    assert not get_navigator(page).exit_requested


def test_back_from_party_detail_returns_to_parties(tmp_path, monkeypatch):
    page = make_page(tmp_path, monkeypatch)
    storage.init_db()
    storage.save_party(
        "ГОСТ", "Партия", "", {"name": "ООО Тест"},
        [{"diameter": 20, "length": 6, "quantity": 1, "volume": "0.230"}],
    )
    open_parties(page)
    open_party_card(page, "Партия")
    assert "Состав партии" in texts(page)

    back(page)

    assert page.appbar.title.value == "Партии"
    assert "Состав партии" not in texts(page)


def test_back_from_counterparties_returns_to_parties(tmp_path, monkeypatch):
    page = make_page(tmp_path, monkeypatch)
    open_parties(page)
    find_button(page, "Контрагенты").on_click(None)
    assert page.appbar.title.value == "Контрагенты"

    back(page)

    assert page.appbar.title.value == "Партии"


def test_back_from_article_returns_to_reference(tmp_path, monkeypatch):
    page = make_page(tmp_path, monkeypatch)
    open_reference(page)
    open_article(page, "Таблица ГОСТ 2708-75")

    back(page)

    assert page.appbar.title.value == "Справочник"


def test_back_closes_party_delete_confirmation(tmp_path, monkeypatch):
    page = make_page(tmp_path, monkeypatch)
    storage.init_db()
    storage.save_party(
        "ГОСТ", "Партия", "", {"name": "ООО Тест"},
        [{"diameter": 20, "length": 6, "quantity": 1, "volume": "0.230"}],
    )
    open_parties(page)
    next(
        action for action in all_controls(page)
        if isinstance(action, ft.IconButton)
        and action.tooltip == "Удалить партию"
    ).on_click(None)
    confirm = page.dialogs[-1]
    assert confirm.title.value == "Удалить партию?"

    back(page)

    assert page.dialogs == []
    assert not confirm.open
    assert page.appbar.title.value == "Партии"


def test_back_does_not_close_calculations_editor(tmp_path, monkeypatch):
    page = make_page(tmp_path, monkeypatch)
    storage.init_db()
    storage.save_party(
        "ГОСТ", "Партия", "", {"name": "ООО Тест"},
        [{"diameter": 20, "length": 6, "quantity": 1, "volume": "0.230"}],
    )
    open_parties(page)
    open_party_card(page, "Партия")
    next(
        control for control in all_controls(page)
        if isinstance(control, ft.OutlinedButton)
        and text_of(control) == "Изменить расчёты"
    ).on_click(None)
    next(
        control for control in walk(page.dialogs[-1])
        if isinstance(control, ft.FilledButton) and text_of(control) == "Изменить"
    ).on_click(None)
    editor = page.dialogs[-1]
    assert editor.title.value == "Изменить расчёты"

    back(page)

    # The editor stays open: only its buttons can close it.
    assert page.dialogs[-1] is editor
    assert editor.open
    assert get_navigator(page).route == "/party/1"
