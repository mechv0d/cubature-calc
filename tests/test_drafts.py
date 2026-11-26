"""Draft persistence and screen-awake helpers."""

from decimal import Decimal

import flet as ft
from test_app_smoke import FakePage, all_controls, find_button, open_gost_screen

from app import screen_utils, storage
from main import main


def test_draft_roundtrip_preserves_decimals(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.sqlite3")
    storage.init_db()

    state = {
        "items": [{"volume": Decimal("1.2300"), "quantity": 2}],
        "length": 6.0,
        "tab": "summary",
    }
    storage.save_draft("sample", state)

    restored = storage.load_draft("sample")
    assert restored == state
    assert isinstance(restored["items"][0]["volume"], Decimal)


def test_gost_draft_survives_restart(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.sqlite3")

    first = FakePage()
    main(first)
    open_gost_screen(first)
    find_button(first, "20").on_click(None)

    # A brand-new page/session must restore the same intermediate result.
    second = FakePage()
    main(second)
    open_gost_screen(second)

    assert any(
        isinstance(control, ft.Text) and control.value == "0.230 м³"
        for control in all_controls(second)
    )
    assert any(
        isinstance(control, ft.Text) and control.value == "6.0 м"
        for control in all_controls(second)
    )


class ServicePage:
    def __init__(self):
        self.services = []
        self.tasks = []

    def run_task(self, handler, *args):
        self.tasks.append((handler, args))


def test_wakelock_is_attached_only_once(monkeypatch):
    monkeypatch.setattr(screen_utils, "_wakelocks", {})
    page = ServicePage()

    screen_utils.keep_screen_awake(page)
    screen_utils.keep_screen_awake(page)

    assert len(page.services) == 1
    assert isinstance(page.services[0], ft.Wakelock)
    assert len(page.tasks) == 2

    screen_utils.allow_screen_sleep(page)
    assert len(page.tasks) == 3


def test_vibrate_attaches_service_and_uses_real_vibration(monkeypatch):
    monkeypatch.setattr(screen_utils, "_haptics", {})
    page = ServicePage()

    # The first tap must attach the service itself (screens may have been
    # built before the service existed) and use ``vibrate`` rather than the
    # silent-on-many-phones ``selection_click`` tick.
    screen_utils.vibrate(page)

    assert len(page.services) == 1
    assert isinstance(page.services[0], ft.HapticFeedback)
    assert len(page.tasks) == 1
    _, args = page.tasks[0]
    # Two pulses make the feedback roughly twice as strong as before.
    assert args == (page.services[0], ("heavy_impact", "vibrate"))
