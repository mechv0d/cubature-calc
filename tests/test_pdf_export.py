"""PDF export hands the file to the client in web mode."""

import asyncio
from types import SimpleNamespace

import flet as ft
from test_app_smoke import FakePage, all_controls, text_of, walk

from app import pdf_export, storage
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


def test_pdf_export_web_mode_downloads_bytes(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.sqlite3")
    # A separate directory proves web export writes nothing to the server.
    server_dir = tmp_path / "server"
    server_dir.mkdir()
    monkeypatch.setattr(pdf_export, "DATA_DIR", server_dir)
    storage.init_db()
    storage.save_party(
        "ГОСТ", "Партия", "", {"name": "ООО Тест"},
        [{"diameter": 20, "length": 6, "quantity": 2, "volume": "0.4600"}],
    )

    pickers = []

    def make_picker():
        picker = FakeFilePicker()
        pickers.append(picker)
        return picker

    monkeypatch.setattr(ft, "FilePicker", make_picker)

    page = WebPage()
    main(page)
    page.navigation_bar.on_change(
        SimpleNamespace(control=SimpleNamespace(selected_index=1))
    )
    tile = next(
        control for control in all_controls(page)
        if isinstance(control, ft.Container)
        and control.on_click is not None
        and any(
            isinstance(child, ft.Text) and child.value == "Партия"
            for child in walk(control)
        )
    )
    tile.on_click(None)

    export_button = next(
        control for control in all_controls(page)
        if isinstance(control, ft.FilledButton)
        and text_of(control) == "Точковка PDF"
    )
    asyncio.run(export_button.on_click(None))

    assert len(pickers) == 1
    saved = pickers[0].saved
    assert saved is not None
    assert saved["file_name"].endswith(".pdf")
    assert saved["file_type"] == ft.FilePickerFileType.CUSTOM
    assert saved["src_bytes"].startswith(b"%PDF")
    assert pickers[0] in page.services
    # No PDF file is left behind on the server in web mode.
    assert list(server_dir.glob("*.pdf")) == []


def test_pdf_bytes_are_rendered_in_memory(tmp_path, monkeypatch):
    monkeypatch.setattr(pdf_export, "DATA_DIR", tmp_path)
    party = {
        "id": 7, "name": "Партия", "type": "ГОСТ",
        "updated_at": "2026-01-01T10:00:00",
        "payload": [
            {"diameter": 20, "length": 6, "quantity": 2, "volume": "0.4600"},
        ],
    }

    pdf_bytes = pdf_export.create_party_pdf_bytes(party)

    assert pdf_bytes.startswith(b"%PDF")
    assert list(tmp_path.glob("*.pdf")) == []
