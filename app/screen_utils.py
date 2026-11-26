"""Shared helpers for calculation screens.

Every calculation screen should call :func:`keep_screen_awake` when it opens
and persist its intermediate state with :func:`save_screen_state`.  The home
screen calls :func:`allow_screen_sleep` so the device may sleep outside of a
calculation.

Drafts are stored per screen name in SQLite, so a screen restored after the
app (or the whole phone) was switched off starts from exactly the same values.
New screens only need to pick a unique name and save a JSON-friendly dict.
"""

import logging
import sqlite3

import flet as ft

from app.storage import clear_draft, load_draft, save_draft

logger = logging.getLogger(__name__)

# Keep a strong reference per page so the services are not garbage collected.
_wakelocks = {}
_haptics = {}

_STORAGE_ERRORS = (sqlite3.Error, OSError, TypeError, ValueError)


def load_screen_state(screen):
    """Load a saved draft; never raises and returns an empty dict if absent."""
    try:
        return load_draft(screen) or {}
    except _STORAGE_ERRORS:
        logger.warning("Could not load draft %r", screen, exc_info=True)
        return {}


def save_screen_state(screen, state):
    """Save a draft; persistence errors must not break the calculator."""
    try:
        save_draft(screen, state)
    except _STORAGE_ERRORS:
        logger.warning("Could not save draft %r", screen, exc_info=True)


def clear_screen_state(screen):
    """Remove a saved draft after its calculation has been saved as a party."""
    try:
        clear_draft(screen)
    except _STORAGE_ERRORS:
        logger.warning("Could not clear draft %r", screen, exc_info=True)


def setup_haptic(page):
    """Register a haptic feedback service for the page.

    Call this once when a calculation screen is built, before ``page.update()``.
    """
    services = getattr(page, "services", None)
    if services is None:
        # Test/dummy pages and platforms without service support.
        return

    service = _haptics.get(id(page))
    if service is None:
        service = ft.HapticFeedback()
        _haptics[id(page)] = service
    if all(existing is not service for existing in services):
        services.append(service)


async def _play_haptic(service, methods):
    # ``heavy_impact`` + ``vibrate`` is roughly twice as strong as the single
    # tick that was used before. Some Android builds silently ignore one of the
    # methods, so try each in turn and keep going until one works.
    if isinstance(methods, str):
        methods = (methods,)
    played = False
    for name in methods:
        try:
            await getattr(service, name)()
            played = True
        except Exception:
            logger.warning(
                "Could not play haptic feedback (%s)", name, exc_info=True
            )
    if not played:
        # Older Flet builds / devices may only support the selection tick.
        try:
            await service.selection_click()
        except Exception:
            logger.warning("Could not play haptic feedback", exc_info=True)


def vibrate(page, methods=("heavy_impact", "vibrate")):
    """Play a strong haptic feedback after adding a calculation item.

    Two pulses (a heavy impact followed by a vibration) are about twice as
    strong as the previous single ``selection_click`` tick, which many phones
    ignored completely or played too softly to notice.
    """
    service = _haptics.get(id(page))
    if service is None:
        # The screen was built before a service could be registered (or the
        # registry dropped it): attach it lazily so the first tap already works.
        setup_haptic(page)
        service = _haptics.get(id(page))
    if service is None:
        return
    run_task = getattr(page, "run_task", None)
    if run_task is None:
        return
    try:
        run_task(_play_haptic, service, methods)
    except Exception:
        logger.warning("Could not schedule haptic feedback", exc_info=True)


async def _enable_wakelock(service):
    try:
        await service.enable()
    except Exception:
        logger.warning("Could not enable wakelock", exc_info=True)


async def _disable_wakelock(service):
    try:
        await service.disable()
    except Exception:
        logger.warning("Could not disable wakelock", exc_info=True)


def keep_screen_awake(page):
    """Prevent the device screen from dimming/sleeping on a calculation screen."""
    services = getattr(page, "services", None)
    if services is None:
        # Test/dummy pages and platforms without service support: nothing to do.
        return

    service = _wakelocks.get(id(page))
    if service is None:
        service = ft.Wakelock()
        _wakelocks[id(page)] = service

    if all(existing is not service for existing in services):
        services.append(service)

    run_task = getattr(page, "run_task", None)
    if run_task is not None:
        try:
            run_task(_enable_wakelock, service)
        except Exception:
            logger.warning("Could not schedule wakelock enable", exc_info=True)


def allow_screen_sleep(page):
    """Let the device sleep again after leaving a calculation screen."""
    service = _wakelocks.get(id(page))
    if service is None:
        return

    run_task = getattr(page, "run_task", None)
    if run_task is not None:
        try:
            run_task(_disable_wakelock, service)
        except Exception:
            logger.warning("Could not schedule wakelock disable", exc_info=True)
