"""Обработка системной кнопки «Назад» (Android back button / edge swipe).

Flet показывает один корневой ``View``, поэтому системный «Назад» нужно
перехватывать самостоятельно: у корневого view отключается автопереход
(``can_pop = False``), а при нажатии вызывается :meth:`Navigator.handle_back`.
Навигатор хранит стек экранов и решает, куда вернуться:

* открыт диалог — он закрывается (кроме защищённых редакторов);
* у экрана есть свой обработчик (например, вкладка «Итоги») — он решает;
* это вложенный экран — открывается предыдущий;
* это один из главных экранов — для выхода нужно нажать «Назад» дважды.
"""

import logging
import time
import weakref

import flet as ft

logger = logging.getLogger(__name__)

#: Значение :attr:`flet.Control.data` у диалогов, которые нельзя закрыть
#: кнопкой «Назад» (например, редактор расчётов партии).
BACK_BLOCKED = "back-blocked"

#: Сколько секунд действует первое нажатие «Назад» на главном экране.
EXIT_WINDOW_SECONDS = 2.0

EXIT_WARNING = "Нажмите «Назад» ещё раз, чтобы выйти из приложения"

#: Навигаторы по страницам. ``ft.Page`` не хешируется, поэтому ключ — ``id``,
#: как у сервисов в ``app/screen_utils.py``.
_NAVIGATORS = {}


def _remember(page, navigator):
    try:
        reference = weakref.ref(page)
    except TypeError:
        return
    _NAVIGATORS[id(page)] = (navigator, reference)


def get_navigator(page):
    """Навигатор страницы или ``None``, если он ещё не создан."""
    entry = _NAVIGATORS.get(id(page))
    if entry is None:
        return None
    navigator, reference = entry
    if reference() is not page:
        # id переиспользован уже удалённой страницей.
        _NAVIGATORS.pop(id(page), None)
        return None
    return navigator


def is_back_blocked(control):
    """True, если диалог защищён от закрытия кнопкой «Назад»."""
    return getattr(control, "data", None) == BACK_BLOCKED


def open_dialogs(page):
    """Открытые модальные диалоги, верхний — последним."""
    container = getattr(page, "_dialogs", None)
    controls = getattr(container, "controls", None)
    if controls is None:
        # Тестовая страница хранит диалоги в обычном списке.
        controls = getattr(page, "dialogs", None)
    if not controls:
        return []
    return [
        dialog for dialog in controls
        if isinstance(dialog, ft.AlertDialog)
        and getattr(dialog, "open", True)
    ]


class Navigator:
    """Стек экранов приложения и обработка системного «Назад»."""

    def __init__(self, page, clock=time.monotonic):
        self.page = page
        self.clock = clock
        #: [(route, builder)] — последний элемент это видимый экран.
        self.stack = []
        self._last_exit_press = None
        self._screen_back = None
        #: True, когда пользователь подтвердил выход из приложения.
        self.exit_requested = False
        _remember(page, self)

    # ---------------------------------------------------------------- стек

    def reset(self, route, builder):
        """Сделать экран главным: «Назад» на нём выходит из приложения."""
        self.stack = [(route, builder)]
        self._screen_back = None
        self._last_exit_press = None
        self.exit_requested = False

    def push(self, route, builder):
        """Открыть вложенный экран поверх текущего."""
        if self.stack and self.stack[-1][0] == route:
            self.stack[-1] = (route, builder)
        else:
            self.stack.append((route, builder))
        self._screen_back = None
        self._last_exit_press = None
        self.exit_requested = False

    @property
    def route(self):
        return self.stack[-1][0] if self.stack else "/"

    @property
    def is_root(self):
        return len(self.stack) <= 1

    def on_screen_back(self, handler):
        """Экранный обработчик: возвращает True, если сам обработал «Назад»."""
        self._screen_back = handler

    def clear_screen_back(self):
        self._screen_back = None

    # ------------------------------------------------------------ системное

    def attach(self):
        """Перехватить системный «Назад» на корневом view."""
        views = getattr(self.page, "views", None) or []
        if not views:
            return
        view = views[0]
        view.can_pop = False
        view.on_confirm_pop = self.handle_back

    async def _confirm(self, should_pop):
        """Разрешить или отменить системный переход назад."""
        views = getattr(self.page, "views", None) or []
        if not views:
            return
        try:
            await views[0].confirm_pop(should_pop)
        except Exception:  # pragma: no cover - только защита от сбоев UI
            logger.warning("Could not confirm view pop", exc_info=True)

    # -------------------------------------------------------------- back

    async def handle_back(self, event=None):
        """Обработать нажатие «Назад» (вызывается из ``on_confirm_pop``)."""
        page = self.page

        # 1. Открыт диалог: «Назад» закрывает его.
        dialogs = open_dialogs(page)
        if dialogs:
            dialog = dialogs[-1]
            if not is_back_blocked(dialog):
                page.pop_dialog()
            await self._confirm(False)
            return

        # 2. Экранный обработчик (вкладки «Таблица» / «Итоги»).
        if self._screen_back is not None and self._screen_back():
            await self._confirm(False)
            return

        # 3. Возврат на предыдущий экран.
        if not self.is_root:
            self.stack.pop()
            _route, builder = self.stack[-1]
            builder()
            await self._confirm(False)
            return

        # 4. Главный экран: выходим только по второму нажатию.
        now = self.clock()
        if (
            self._last_exit_press is not None
            and now - self._last_exit_press <= EXIT_WINDOW_SECONDS
        ):
            self._last_exit_press = None
            self.exit_requested = True
            await self._confirm(True)
            return
        self._last_exit_press = now
        page.show_dialog(ft.SnackBar(content=ft.Text(EXIT_WARNING)))
        await self._confirm(False)
