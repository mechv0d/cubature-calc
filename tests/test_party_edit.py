"""Party detail screen: editing positions and Excel export."""

import asyncio
from types import SimpleNamespace

import flet as ft
from test_app_smoke import FakePage, all_controls, text_of, walk

from app import excel_export, storage
from main import main


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


def save_party():
    storage.init_db()
    return storage.save_party(
        "ГОСТ", "Партия", "Описание", {"name": "ООО Тест"},
        [{"diameter": 20, "length": 6, "quantity": 1, "volume": "0.230",
          "price_per_m3": "1000", "cost": "230"}],
    )


def find_party_card(page, name):
    """Кликабельная карточка партии по её названию."""
    for control in all_controls(page):
        if not isinstance(control, ft.Container):
            continue
        if control.on_click is None:
            continue
        texts = [
            child.value for child in walk(control)
            if isinstance(child, ft.Text)
        ]
        if name in texts:
            return control
    raise AssertionError(f"party card {name} not found")


def open_party(page, name="Партия"):
    page.navigation_bar.on_change(
        SimpleNamespace(control=SimpleNamespace(selected_index=1))
    )
    find_party_card(page, name).on_click(None)


def test_party_detail_has_excel_and_icon_only_actions(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.sqlite3")
    save_party()

    page = FakePage()
    main(page)
    open_party(page)

    controls = list(all_controls(page))
    assert any(
        isinstance(control, ft.FilledButton)
        and text_of(control) == "Расчёт Excel"
        for control in controls
    )
    delete_button = next(
        control for control in controls
        if isinstance(control, ft.OutlinedButton)
        and text_of(control) == "Удалить"
    )
    edit_button = next(
        control for control in controls
        if isinstance(control, ft.OutlinedButton)
        and text_of(control) == "Изменить расчёты"
    )
    assert delete_button.style.bgcolor == "#FFFFFF"
    assert edit_button.style.bgcolor == "#FFFFFF"
    assert delete_button.style.side.color == "#F8C8C5"
    assert edit_button.style.side.color == "#C7DDF4"

    # The header keeps a single edit action and no delete action.
    header_actions = page.appbar.actions
    assert len(header_actions) == 1
    assert header_actions[0].icon == ft.Icons.EDIT_NOTE


def test_edit_calculations_asks_for_confirmation_and_saves_quantity(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.sqlite3")
    save_party()

    page = FakePage()
    main(page)
    open_party(page)

    edit_button = next(
        control for control in all_controls(page)
        if isinstance(control, ft.OutlinedButton)
        and text_of(control) == "Изменить расчёты"
    )
    edit_button.on_click(None)

    confirm = page.dialogs[-1]
    assert confirm.title.value == "Изменить расчёты?"
    next(
        control for control in walk(confirm)
        if isinstance(control, ft.FilledButton)
        and text_of(control) == "Изменить"
    ).on_click(None)

    editor = page.dialogs[-1]
    assert editor.title.value == "Изменить расчёты"
    quantity_field = next(
        control for control in walk(editor)
        if isinstance(control, ft.TextField)
        and control.text_align == ft.TextAlign.CENTER
    )
    quantity_field.value = "3"
    quantity_field.on_change(SimpleNamespace(control=quantity_field))

    next(
        control for control in walk(editor)
        if isinstance(control, ft.FilledButton)
        and text_of(control) == "Сохранить"
    ).on_click(None)

    payload = storage.list_parties()[0]["payload"]
    assert payload[0]["quantity"] == 3
    assert payload[0]["volume"] == "0.690"


def save_lumber_party():
    storage.init_db()
    return storage.save_party(
        "Пиломатериал", "Пиломатериал 01.01.2026", "", {"name": "ООО Тест"},
        [{"thickness_cm": 5, "width_cm": 5, "length_m": 6,
          "quantity": 25, "volume_m3": "0.3750", "price_per_m3": "1000"}],
    )


def test_lumber_party_position_is_shown_in_millimetres(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.sqlite3")
    save_lumber_party()

    page = FakePage()
    main(page)
    open_party(page, name="Пиломатериал 01.01.2026")

    texts = [
        control.value for control in all_controls(page)
        if isinstance(control, ft.Text)
    ]
    # 5 cm × 5 cm becomes 50 × 50 mm without the "Пиломатериал" prefix.
    assert "50×50 мм" in texts
    assert not any(
        isinstance(text, str) and text.startswith("Пиломатериал 5×5")
        for text in texts
    )

    from main import party_calculation_data

    party = storage.list_parties()[0]
    assert party_calculation_data(party)["rows"][0]["label"] == "50×50 мм"


def test_asset_url_adds_version_from_file_mtime():
    from main import ASSETS_DIR, asset_url

    url = asset_url("pilomaterial.png")
    expected = int((ASSETS_DIR / "pilomaterial.png").stat().st_mtime)
    assert url == f"pilomaterial.png?v={expected}"

    # Remote and absolute URLs are used as is.
    assert asset_url("https://example.com/a.png") == "https://example.com/a.png"
    assert asset_url("/static/a.png") == "/static/a.png"
    # Missing files stay unchanged instead of breaking the image.
    assert asset_url("missing.png") == "missing.png"


def test_party_lumber_icon_gets_cache_busting_version(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.sqlite3")
    storage.init_db()
    storage.save_party(
        "Пиломатериал", "Партия", "", {"name": "ООО Тест"},
        [{"thickness_cm": 5, "width_cm": 5, "length_m": 6,
          "quantity": 1, "volume_m3": "0.0150"}],
    )

    page = FakePage()
    main(page)
    page.navigation_bar.on_change(
        SimpleNamespace(control=SimpleNamespace(selected_index=1))
    )

    icon = next(
        control for control in all_controls(page)
        if isinstance(control, ft.Image)
        and str(control.src).startswith("pilomaterial.png")
    )
    assert "?v=" in icon.src

    # The icon uses the configured size and is not inside a ListTile (which
    # would clamp it to ~56 px and make the picture smaller).
    from main import PARTY_ICON_SIZE

    assert icon.width == PARTY_ICON_SIZE
    assert icon.height == PARTY_ICON_SIZE

    card = next(
        control for control in all_controls(page)
        if isinstance(control, ft.Card)
    )
    assert isinstance(card.shape, ft.RoundedRectangleBorder)
    assert card.shape.side is not None
    assert card.shape.side.width == 1

    # ListTile clamps ``leading`` to ~56 px, so the party card uses a plain
    # Row instead; otherwise a bigger image would be scaled back down.
    assert not any(
        isinstance(control, ft.ListTile)
        and any(
            isinstance(child, ft.Text) and child.value == "Партия"
            for child in walk(control)
        )
        for control in all_controls(page)
    )


def test_party_card_description_is_limited_to_three_lines(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.sqlite3")
    storage.init_db()
    long_description = "\n".join(f"Строка {number}" for number in range(1, 7))
    storage.save_party(
        "ГОСТ", "Длинная партия", long_description, {"name": "ООО Тест"},
        [{"diameter": 20, "length": 6, "quantity": 1, "volume": "0.230"}],
    )

    page = FakePage()
    main(page)
    page.navigation_bar.on_change(
        SimpleNamespace(control=SimpleNamespace(selected_index=1))
    )

    description = next(
        control for control in walk(find_party_card(page, "Длинная партия"))
        if isinstance(control, ft.Text)
        and str(control.value).startswith("Строка 1")
    )
    assert description.max_lines == 3
    assert description.overflow == ft.TextOverflow.ELLIPSIS


def test_party_detail_shows_position_and_total_cost(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.sqlite3")
    save_party()

    page = FakePage()
    main(page)
    open_party(page)

    texts = [
        control.value for control in all_controls(page)
        if isinstance(control, ft.Text)
    ]
    # One position: 0.230 m³ × 1000 ₽/м³ = 230 ₽, both per row and in totals.
    assert "230.00" in texts
    assert texts.count("230.00") == 2
    assert "230.00 ₽" in texts
    assert "Сумма, ₽" in texts
    # Volume rows have no unit: it is already in the column header.
    assert "0.230" in texts
    assert texts.count("0.230 м³") == 1


def test_party_detail_without_prices_shows_dashes(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.sqlite3")
    storage.init_db()
    storage.save_party(
        "ГОСТ", "Без цены", "", {"name": "ООО Тест"},
        [{"diameter": 20, "length": 6, "quantity": 1, "volume": "0.230",
          "price_per_m3": "0", "cost": "0"}],
    )

    page = FakePage()
    main(page)
    open_party(page, name="Без цены")

    texts = [
        control.value for control in all_controls(page)
        if isinstance(control, ft.Text)
    ]
    assert "—" in texts
    assert "Цена 1 м³: н/д" in " ".join(str(text) for text in texts)


def test_party_excel_export_downloads_bytes(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.sqlite3")
    server_dir = tmp_path / "server"
    server_dir.mkdir()
    monkeypatch.setattr(excel_export, "DATA_DIR", server_dir)
    save_party()

    pickers = []

    def make_picker():
        picker = FakeFilePicker()
        pickers.append(picker)
        return picker

    monkeypatch.setattr(ft, "FilePicker", make_picker)

    page = WebPage()
    main(page)
    open_party(page)

    export_button = next(
        control for control in all_controls(page)
        if isinstance(control, ft.FilledButton)
        and text_of(control) == "Расчёт Excel"
    )
    asyncio.run(export_button.on_click(None))

    assert len(pickers) == 1
    saved = pickers[0].saved
    assert saved["file_name"].endswith(".xlsx")
    assert saved["src_bytes"].startswith(b"PK")
    assert list(server_dir.glob("*.xlsx")) == []
