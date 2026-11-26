"""Тесты справочника: разбор Markdown и экраны списка и статьи."""

import re

import flet as ft
import pytest

from app import storage
from app.content.guide import (
    ARTICLES,
    Article,
    load_article_body,
)
from app.content.markdown import parse_blocks, parse_inline
from main import main

VISIBLE_ARTICLES = tuple(article for article in ARTICLES if article.active)


class FakePage:
    """Минимальная замена ft.Page: контролы собираются без окна."""

    width = 390
    height = 844

    def __init__(self):
        self.controls = []
        self.title = None
        self.appbar = None
        self.navigation_bar = None
        self.bgcolor = None
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


def texts(page):
    return [
        control.value
        for control in all_controls(page)
        if isinstance(control, ft.Text) and control.value
    ]


def visible_text(page):
    """Весь видимый текст, включая абзацы, собранные из TextSpan."""
    return control_text(page)


def control_text(control):
    parts = []
    for item in walk(control):
        if not isinstance(item, ft.Text):
            continue
        if item.value:
            parts.append(item.value)
        for span in item.spans or []:
            if span.text:
                parts.append(span.text)
    return " ".join(parts)


def images(page):
    # Local images carry a ``?v=<mtime>`` cache-busting suffix; tests compare
    # the logical asset paths.
    return [
        str(control.src).split("?", 1)[0]
        for control in all_controls(page)
        if isinstance(control, ft.Image)
    ]


def open_reference(page):
    event = type(
        "Event", (), {"control": type("Control", (), {"selected_index": 2})()}
    )()
    page.navigation_bar.on_change(event)


def article_cards(page):
    return [
        control
        for control in all_controls(page)
        if isinstance(control, ft.Container)
        and control.on_click is not None
        and control.border_radius == 20
    ]


def open_article(page, title):
    card = next(
        card for card in article_cards(page)
        if title in control_text(card)
    )
    card.on_click(None)


@pytest.fixture
def page(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.sqlite3")
    fake = FakePage()
    main(fake)
    return fake


# --- Разбор Markdown -------------------------------------------------------


def test_parse_blocks_recognises_supported_blocks():
    blocks = parse_blocks(
        "Вступление.\n\n"
        "## Толщина\n\n"
        "- Первый пункт,\n"
        "  продолжение пункта.\n"
        "- Второй пункт.\n\n"
        "1. Раз\n"
        "2. Два\n\n"
        "![Подпись](guide/inline.png)\n\n"
        "> Цитата.\n\n"
        "---\n"
    )

    assert [block.kind for block in blocks] == [
        "paragraph", "heading", "bullets", "ordered", "image", "quote", "divider",
    ]
    assert blocks[1].text == "Толщина"
    assert blocks[1].level == 2
    assert blocks[2].items == (
        "Первый пункт, продолжение пункта.",
        "Второй пункт.",
    )
    assert blocks[4].src == "guide/inline.png"
    assert blocks[4].caption == "Подпись"
    assert blocks[5].text == "Цитата."


def test_parse_inline_marks_bold_italic_code_and_links():
    spans = parse_inline("**жирный** *курсив* `код` [ссылка](https://example.org)")

    assert [(span.text, span.bold, span.italic, span.code) for span in spans] == [
        ("жирный", True, False, False),
        (" ", False, False, False),
        ("курсив", False, True, False),
        (" ", False, False, False),
        ("код", False, False, True),
        (" ", False, False, False),
        ("ссылка", False, False, False),
    ]
    assert spans[-1].url == "https://example.org"


def test_every_article_has_markdown_text():
    for article in ARTICLES:
        blocks = parse_blocks(load_article_body(article))
        assert len(blocks) >= 8, article.slug
        assert any(block.kind == "heading" for block in blocks), article.slug


def test_missing_markdown_file_does_not_crash():
    body = load_article_body(Article("no-such-article", "Нет", "Нет"))

    assert "Текст не найден" in body
    assert parse_blocks(body)


def test_asset_extension_is_resolved_automatically(tmp_path, monkeypatch):
    from app.content import guide

    monkeypatch.setattr(guide, "ASSET_ROOT", tmp_path)
    (tmp_path / "measure.jpg").write_bytes(b"jpg")

    assert guide.resolve_asset("guide/measure.png") == "guide/measure.jpg"
    assert guide.resolve_asset("guide/measure.jpg") == "guide/measure.jpg"
    # Нет ни одного варианта — ссылка остаётся как в тексте.
    assert guide.resolve_asset("guide/nothing.png") == "guide/nothing.png"


# --- Экран списка ----------------------------------------------------------


def test_reference_screen_lists_all_articles(page):
    open_reference(page)

    assert page.navigation_bar is not None
    assert isinstance(page.appbar, ft.AppBar)
    assert page.appbar.title.value == "Справочник"
    assert page.appbar.bgcolor == "#176B4A"

    assert len(article_cards(page)) == len(VISIBLE_ARTICLES)

    for article in VISIBLE_ARTICLES:
        assert article.title in texts(page)
        assert article.subtitle in texts(page)
        assert article.cover in images(page)

    for article in ARTICLES:
        if not article.active:
            assert article.title not in texts(page)


def test_reference_thumbnails_are_large_and_square(page):
    open_reference(page)

    covers = [
        control
        for control in all_controls(page)
        if isinstance(control, ft.Image)
        and str(control.src).split("?", 1)[0] in {
            article.cover for article in VISIBLE_ARTICLES
        }
    ]

    assert len(covers) == len(VISIBLE_ARTICLES)
    for cover in covers:
        assert cover.width == cover.height
        assert cover.width >= 96
        assert cover.fit == "cover"


def test_disclaimer_closes_the_list_and_uses_new_name(page):
    open_reference(page)

    assert "Неофициальное приложение" in texts(page)
    body = next(
        text for text in texts(page) if "не связана с Росстандартом" in text
    )
    assert "Кубатура Экспресс" in body
    assert "Кубатурник" not in body
    assert "ГОСТ 2708-75" in body


# --- Экран статьи ----------------------------------------------------------


def test_article_screen_renders_hero_text_and_inline_image(page):
    open_reference(page)
    open_article(page, "Таблица ГОСТ 2708-75")

    assert page.navigation_bar is None
    assert page.appbar is None
    assert "Таблица ГОСТ 2708-75" in texts(page)
    # The guide text is edited separately, so match the word stem instead of
    # one exact phrase ("верхний торец" / "верхнему торцу" / ...).
    body = visible_text(page)
    assert any(form in body for form in ("верхний торец", "верхнему", "верхнего"))
    assert any(src.startswith("guide/gost-table") for src in images(page))
    assert "guide/inline-rounding.png" in images(page)


def test_article_body_is_built_from_markdown(page):
    open_reference(page)
    open_article(page, "Сколько досок в кубе")

    body = load_article_body(
        next(article for article in ARTICLES if article.slug == "boards")
    )
    first_paragraph = next(
        block for block in parse_blocks(body) if block.kind == "paragraph"
    )
    assert first_paragraph.text[:30] in visible_text(page)
    # Inline images come from the Markdown itself, so the test follows the
    # content: whenever the article has a ``![](guide/...)`` it must render.
    inline = re.search(r"!\[[^\]]*\]\((guide/[^)\s]+)\)", body)
    if inline:
        assert inline.group(1) in images(page)


def test_inline_images_fit_the_text_column(page):
    open_reference(page)
    open_article(page, "Таблица ГОСТ 2708-75")

    inline = next(
        control for control in all_controls(page)
        if isinstance(control, ft.Image)
        and str(control.src).split("?", 1)[0] == "guide/inline-rounding.png"
    )
    assert inline.width == FakePage.width - 36
    assert inline.error_content is not None


def test_back_button_returns_to_the_list(page):
    open_reference(page)
    open_article(page, "Таблица ГОСТ 2708-75")

    back = next(
        control for control in all_controls(page)
        if isinstance(control, ft.Container)
        and control.on_click is not None
        and control.width == 44
    )
    back.on_click(None)

    assert len(article_cards(page)) == len(VISIBLE_ARTICLES)
