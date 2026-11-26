"""Содержимое раздела «Справочник».

Метаданные статей хранятся отдельными JSON-файлами в каталоге
``app/content/guide`` (по одному ``<slug>.json`` на статью), тексты —
Markdown-файлы рядом.  Картинки лежат в ``assets/guide`` (рядом с ``main.py``,
каталог передаётся в ``ft.run`` как ``assets_dir``) и подключаются
в тексте как ``guide/<файл>.png``.

Чтобы добавить статью, достаточно:

1. положить рядом с остальными ``<slug>.md``;
2. положить ``<slug>.json`` с полями ``title``, ``subtitle``, ``order`` и
   ``active`` (slug берётся из имени файла);
3. положить картинки ``<slug>-square.jpg`` (квадрат для списка) и
   ``<slug>.jpg`` (широкая шапка). Без них покажется заглушка.
"""

import json
from dataclasses import dataclass
from pathlib import Path

CONTENT_DIR = Path(__file__).resolve().parent / "guide"
#: ``app/content/guide.py`` → корень проекта → ``assets/guide``.
ASSET_ROOT = Path(__file__).resolve().parent.parent.parent / "assets" / "guide"

#: Каталог картинок внутри ``assets_dir``.
ASSET_DIR = "guide"

#: Поддерживаемые расширения — можно класть и .jpg, и .png.
ASSET_EXTENSIONS = ("jpg", "jpeg", "png", "webp")


def resolve_asset(src: str) -> str:
    """Подставить существующий файл, если расширение в тексте не совпало.

    В Markdown удобно писать ``guide/inline-diameters.png``, а картинку
    положить в ``.jpg`` — тогда ссылка всё равно сработает.
    """
    path = Path(src)
    if (ASSET_ROOT / path.name).is_file():
        return src
    for extension in ASSET_EXTENSIONS:
        candidate = path.with_suffix(f".{extension}")
        if (ASSET_ROOT / candidate.name).is_file():
            return f"{ASSET_DIR}/{candidate.name}"
    return src


def _pick(*names: str) -> str:
    """Первое существующее имя файла, иначе первое из перечисленных."""
    for name in names:
        if (ASSET_ROOT / name).is_file():
            return f"{ASSET_DIR}/{name}"
    return f"{ASSET_DIR}/{names[0]}"


@dataclass(frozen=True)
class Article:
    """Статья справочника: карточка в списке и Markdown-файл с текстом."""

    slug: str
    title: str
    subtitle: str
    active: bool = True
    order: int = 1000

    @property
    def cover(self) -> str:
        """Квадратная обложка для списка статей."""
        return _pick(
            f"{self.slug}-square.jpg",
            f"{self.slug}-square.png",
            f"{self.slug}.jpg",
            f"{self.slug}.png",
            f"{self.slug}-wide.jpg",
            f"{self.slug}-wide.png",
        )

    @property
    def hero(self) -> str:
        """Широкая картинка-шапка экрана статьи."""
        return _pick(
            f"{self.slug}.jpg",
            f"{self.slug}.png",
            f"{self.slug}-wide.jpg",
            f"{self.slug}-wide.png",
            f"{self.slug}-square.jpg",
            f"{self.slug}-square.png",
        )

    @property
    def source(self) -> Path:
        return CONTENT_DIR / f"{self.slug}.md"


def load_articles() -> tuple[Article, ...]:
    """Собрать статьи из JSON-файлов каталога ``CONTENT_DIR``.

    Функция читает каталог при каждом вызове, поэтому правки в JSON
    подхватываются после обновления страницы.  Битый или неполный JSON
    пропускается, чтобы одна опечатка не ломала весь справочник.  Порядок
    задаётся полем ``order`` (по возрастанию), при равенстве — по заголовку.
    """
    articles: list[Article] = []
    for path in sorted(CONTENT_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        slug = str(data.get("slug") or path.stem)
        title = str(data.get("title") or slug)
        subtitle = str(data.get("subtitle") or "")
        active = bool(data.get("active", True))
        try:
            order = int(data.get("order", 1000))
        except (TypeError, ValueError):
            order = 1000
        articles.append(Article(slug, title, subtitle, active, order))

    articles.sort(key=lambda article: (article.order, article.title))
    return tuple(articles)


#: Снимок статей на момент импорта.  Экраны используют :func:`load_articles`,
#: чтобы изменения в JSON подхватывались после обновления страницы.
ARTICLES: tuple[Article, ...] = load_articles()

DISCLAIMER_TITLE = "Неофициальное приложение"
DISCLAIMER_ICON = _pick("log-slice.png", "log-slice.jpg")
DISCLAIMER_TEXT = (
    "Кубатура Экспресс не связана с Росстандартом и органами власти. "
    "Таблицы перенесены из текстов ГОСТ 2708-75, 2292-88 и 3243-88; "
)


def article_by_slug(slug: str) -> Article | None:
    return next(
        (article for article in load_articles() if article.slug == slug), None
    )


def load_article_body(article: Article) -> str:
    """Прочитать Markdown статьи; при ошибке вернуть короткое сообщение."""
    try:
        return article.source.read_text(encoding="utf-8")
    except OSError:
        return (
            "## Текст не найден\n\n"
            f"Файл `{article.source.name}` отсутствует в приложении."
        )
