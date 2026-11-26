"""Небольшой разборщик Markdown для статей справочника.

Поддерживается ровно то, что нужно текстам приложения:

* заголовки ``#`` … ``###``;
* абзацы;
* маркированные (``-``, ``*``, ``+``) и нумерованные (``1.``) списки;
* картинки отдельной строкой — ``![подпись](guide/file.png)``;
* цитаты (``>``) и горизонтальные линии (``---``);
* внутри текста: ``**жирный**``, ``*курсив*``, ``` `код` ``` и ссылки
  ``[текст](адрес)``.

Таблицы, сноски и HTML намеренно не поддерживаются: для справочника они не
нужны, а лишний код пришлось бы тащить в APK.

Разбор не зависит от Flet, поэтому его легко тестировать.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

HEADING_RE = re.compile(r"^(?P<hashes>#{1,6})\s+(?P<text>.+?)\s*#*$")
BULLET_RE = re.compile(r"^\s*[-*+]\s+(?P<text>.+)$")
ORDERED_RE = re.compile(r"^\s*\d+[.)]\s+(?P<text>.+)$")
IMAGE_RE = re.compile(
    r"^!\[(?P<alt>[^\]]*)\]\((?P<src>[^)\s]+)(?:\s+\"[^\"]*\")?\)$"
)
DIVIDER_RE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")
QUOTE_RE = re.compile(r"^\s*>\s?(?P<text>.*)$")

INLINE_RE = re.compile(
    r"\*\*(?P<bold>.+?)\*\*"
    r"|\*(?P<italic>[^*\n]+?)\*"
    r"|`(?P<code>[^`\n]+)`"
    r"|\[(?P<link_text>[^\]\n]+)\]\((?P<link_url>[^)\s]+)(?:\s+\"[^\"]*\")?\)"
)


@dataclass(frozen=True)
class Span:
    """Кусок строки с одинаковым оформлением."""

    text: str
    bold: bool = False
    italic: bool = False
    code: bool = False
    url: str | None = None


@dataclass(frozen=True)
class Block:
    """Блок текста статьи.

    ``kind`` — одно из ``heading``, ``paragraph``, ``bullets``, ``ordered``,
    ``image``, ``quote``, ``divider``.
    """

    kind: str
    text: str = ""
    level: int = 0
    items: tuple[str, ...] = field(default_factory=tuple)
    src: str = ""
    caption: str = ""


def parse_inline(text: str) -> list[Span]:
    """Разбить строку на куски с жирным, курсивом, кодом и ссылками."""
    spans: list[Span] = []
    position = 0
    for match in INLINE_RE.finditer(text):
        if match.start() > position:
            spans.append(Span(text[position:match.start()]))
        if match.group("bold") is not None:
            spans.append(Span(match.group("bold"), bold=True))
        elif match.group("italic") is not None:
            spans.append(Span(match.group("italic"), italic=True))
        elif match.group("code") is not None:
            spans.append(Span(match.group("code"), code=True))
        else:
            spans.append(
                Span(match.group("link_text"), url=match.group("link_url"))
            )
        position = match.end()
    if position < len(text):
        spans.append(Span(text[position:]))
    return [span for span in spans if span.text]


def parse_blocks(markdown: str) -> list[Block]:
    """Разобрать Markdown статьи в список блоков."""
    blocks: list[Block] = []
    paragraph: list[str] = []
    quote: list[str] = []
    list_kind = ""
    list_items: list[str] = []

    def flush_paragraph():
        if paragraph:
            blocks.append(Block("paragraph", text=" ".join(paragraph)))
            paragraph.clear()

    def flush_quote():
        if quote:
            blocks.append(Block("quote", text=" ".join(quote)))
            quote.clear()

    def flush_list():
        nonlocal list_kind
        if list_items:
            blocks.append(
                Block(list_kind, items=tuple(list_items))
            )
            list_items.clear()
        list_kind = ""

    def flush_all():
        flush_paragraph()
        flush_quote()
        flush_list()

    for raw_line in markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw_line.rstrip()
        stripped = line.strip()

        if not stripped:
            flush_all()
            continue

        # Продолжение пункта списка: строка с отступом.
        if list_items and line[:1] == " " and not BULLET_RE.match(line) \
                and not ORDERED_RE.match(line):
            list_items[-1] = f"{list_items[-1]} {stripped}"
            continue

        image = IMAGE_RE.match(stripped)
        if image:
            flush_all()
            blocks.append(
                Block(
                    "image",
                    src=image.group("src"),
                    caption=image.group("alt").strip(),
                )
            )
            continue

        if DIVIDER_RE.match(line):
            flush_all()
            blocks.append(Block("divider"))
            continue

        heading = HEADING_RE.match(line)
        if heading:
            flush_all()
            blocks.append(
                Block(
                    "heading",
                    text=heading.group("text"),
                    level=len(heading.group("hashes")),
                )
            )
            continue

        bullet = BULLET_RE.match(line)
        if bullet:
            flush_paragraph()
            flush_quote()
            if list_kind != "bullets":
                flush_list()
                list_kind = "bullets"
            list_items.append(bullet.group("text").strip())
            continue

        ordered = ORDERED_RE.match(line)
        if ordered:
            flush_paragraph()
            flush_quote()
            if list_kind != "ordered":
                flush_list()
                list_kind = "ordered"
            list_items.append(ordered.group("text").strip())
            continue

        quoted = QUOTE_RE.match(line)
        if quoted:
            flush_paragraph()
            flush_list()
            quote.append(quoted.group("text").strip())
            continue

        flush_quote()
        flush_list()
        paragraph.append(stripped)

    flush_all()
    return blocks
