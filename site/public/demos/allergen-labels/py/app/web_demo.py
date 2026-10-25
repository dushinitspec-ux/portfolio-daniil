"""Adapter for the in-browser demo on the portfolio site (Pyodide, JSON in and out).

It runs the real code: the dictionary matcher, the Kitchen service with its rules (a name
on every change, a confirmation only for the current recipe, an edit resets it), the
append-only SQLite schema and the menu builder. Only the plumbing differs from the server:

- the database is SQLite in memory, reached through a small synchronous stand-in for
  aiosqlite (there are no threads in the browser);
- there is no AI: OfflineSuggester, so unknown ingredients are flagged for the chef;
- the menu starts with a few dishes of the project's sample menu (app/demo.py).
"""

import sqlite3
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

from app import allergens as annex
from app.db import SCHEMA, Confirmation, Event, Repository
from app.demo import DEMO_CHEF, SAMPLE_DISHES, SampleDish, seed
from app.i18n import MENU_TEXT, Language, Section, parse_language
from app.llm import OfflineSuggester
from app.matcher import Analysis, IngredientResult, analyse
from app.menu import build_menu
from app.service import DishView, Kitchen, KitchenError, StaleRecipeError, utcnow
from app.text import recipe_hash

TITLE = "Sample Kitchen"  # Settings.menu_title in demo mode

# Part of the sample menu, so the card looks like a menu: one dish per section and recipes
# written in all four languages. The demo's own run adds the carbonara and the satay.
START_DISHES = (
    "Red lentil soup (mercimek çorbası)",
    "Hummus",
    "Wiener schnitzel",
    "Pelmeni (meat dumplings) with sour cream",
    "Pistachio baklava",
    "Ayran (salted yogurt drink)",
)
SCRIPT_DISHES = ("Spaghetti carbonara", "Chicken satay with peanut sauce")


# --- aiosqlite stand-in --------------------------------------------------------------


class _Cursor:
    def __init__(self, cursor: sqlite3.Cursor) -> None:
        self._cursor = cursor

    @property
    def lastrowid(self) -> int | None:
        return self._cursor.lastrowid

    async def fetchone(self) -> Any:
        return self._cursor.fetchone()

    async def fetchall(self) -> list[Any]:
        return self._cursor.fetchall()


class _Result:
    """What aiosqlite's execute() returns: awaitable, and an async context manager."""

    def __init__(self, run: Callable[[], sqlite3.Cursor]) -> None:
        self._run = run

    async def _cursor(self) -> _Cursor:
        return _Cursor(self._run())

    def __await__(self):  # type: ignore[no-untyped-def]
        return self._cursor().__await__()

    async def __aenter__(self) -> _Cursor:
        return await self._cursor()

    async def __aexit__(self, *exc: object) -> None:
        return None


class SyncConnection:
    """The part of aiosqlite.Connection that Repository uses, on plain sqlite3."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def execute(self, sql: str, parameters: Sequence[Any] = ()) -> _Result:
        return _Result(lambda: self._conn.execute(sql, parameters))

    async def executescript(self, script: str) -> None:
        self._conn.executescript(script)

    async def commit(self) -> None:
        self._conn.commit()

    async def rollback(self) -> None:
        self._conn.rollback()

    async def close(self) -> None:
        self._conn.close()


async def open_repository() -> Repository:
    """Repository.connect(":memory:") without aiosqlite."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db = SyncConnection(conn)
    await db.execute("PRAGMA foreign_keys=ON")
    await db.executescript(SCHEMA)
    await db.commit()
    return Repository(db)  # type: ignore[arg-type]


# --- State of one page ---------------------------------------------------------------


class _State:
    kitchen: Kitchen | None = None
    tz: timezone = UTC


_state = _State()


def _kitchen() -> Kitchen:
    if _state.kitchen is None:
        raise RuntimeError("call setup() first")
    return _state.kitchen


def _sample(name: str) -> SampleDish:
    return next(d for d in SAMPLE_DISHES if d.names[Language.EN] == name)


# --- JSON views ----------------------------------------------------------------------


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds")


def _item(item: IngredientResult) -> dict[str, Any]:
    return {
        "label": item.label,
        "text": item.text,
        "parent": item.parent,
        "status": item.status.value,
        "hits": [
            {
                "allergen": h.allergen,
                "certain": h.certain,
                "found": h.found,
                "term": h.term,
                "language": h.language.value,
            }
            for h in item.hits
        ],
        "notes": item.all_notes,
        "unknown": item.unknown,
        "free_from": item.free_from,
    }


def _analysis(analysis: Analysis) -> dict[str, Any]:
    return {
        "items": [_item(i) for i in analysis.items],
        "allergens": sorted(analysis.allergens),
        "certain": sorted(analysis.certain),
        "to_check": [i.label for i in analysis.to_check],
    }


def _confirmation(c: Confirmation | None) -> dict[str, Any] | None:
    if c is None:
        return None
    return {
        "id": c.id,
        "by": c.confirmed_by,
        "at": _iso(c.confirmed_at),
        "allergens": list(c.allergens),
        "recipe_hash": c.recipe_hash,
    }


def _event(e: Event) -> dict[str, Any]:
    return {"at": _iso(e.at), "actor": e.actor, "action": e.action, "detail": e.detail}


def _summary(v: DishView) -> dict[str, Any]:
    return {
        "id": v.id,
        "names": {lang.value: v.row.names[lang] for lang in Language},
        "section": v.section.value,
        "state": v.state,
        "sample": v.row.updated_by == DEMO_CHEF,
    }


async def _dish(dish_id: int) -> dict[str, Any] | None:
    kitchen = _kitchen()
    v = await kitchen.get(dish_id)
    if v is None:
        return None
    confirmations, events = await kitchen.history(dish_id)
    return {
        **_summary(v),
        "recipe": v.row.recipe,
        "recipe_hash": v.row.recipe_hash,
        "updated_by": v.row.updated_by,
        "updated_at": _iso(v.row.updated_at),
        "confirmed": v.confirmed,
        "confirmation": _confirmation(v.confirmation),
        "last_confirmation": _confirmation(v.last_confirmation),
        "confirmed_allergens": sorted(v.confirmed_allergens),
        "suggested": sorted(v.suggested),
        "preselected": sorted(v.preselected),
        "drift": sorted(v.drift),
        "analysis": _analysis(v.analysis),
        "confirmations": [_confirmation(c) for c in confirmations],
        "events": [_event(e) for e in events],
    }


def _names(names: dict[str, str]) -> dict[Language, str]:
    return {lang: str(names.get(lang.value, "")) for lang in Language}


def _section(value: str) -> Section:
    try:
        return Section(value)
    except ValueError:
        return Section.MAINS


# --- Entry points (called from the page) ---------------------------------------------


async def setup(utc_offset_minutes: int = 0) -> dict[str, Any]:
    """A fresh kitchen: empty in-memory database, then part of the sample menu.

    `utc_offset_minutes` is the visitor's offset, used for the "last update" date on the
    menu (a fixed offset: the browser has no time zone database here).
    """
    _state.tz = timezone(timedelta(minutes=int(utc_offset_minutes)))
    kitchen = Kitchen(await open_repository(), OfflineSuggester())
    await seed(kitchen, utcnow(), [_sample(name) for name in START_DISHES])
    _state.kitchen = kitchen
    return {
        "title": TITLE,
        "demo_chef": DEMO_CHEF,
        "ai": kitchen.suggester.enabled,
        "languages": [lang.value for lang in Language],
        "sections": [
            {"id": s.value, "label": {lang.value: s.label(lang) for lang in Language}}
            for s in Section
        ],
        "allergens": [
            {
                "number": a.number,
                "id": a.id,
                "label": {lang.value: a.label(lang) for lang in Language},
                "name": {lang.value: a.name(lang) for lang in Language},
            }
            for a in annex.ALLERGENS
        ],
        # The two sample dishes the autoplay types in, with the satay's later edit.
        "script": [
            {
                "names": {lang.value: d.names[lang] for lang in Language},
                "section": d.section.value,
                "recipe": d.recipe,
                "changed_recipe": d.changed_recipe,
            }
            for d in map(_sample, SCRIPT_DISHES)
        ],
        "dishes": await dishes(),
    }


def check(recipe: str) -> dict[str, Any]:
    """Dictionary analysis of an ingredient list, without saving (POST /api/check)."""
    return {**_analysis(analyse(recipe)), "hash": recipe_hash(recipe)}


async def dishes() -> list[dict[str, Any]]:
    return [_summary(v) for v in await _kitchen().dishes()]


async def dish(dish_id: int) -> dict[str, Any] | None:
    return await _dish(int(dish_id))


async def save(
    dish_id: int | None, names: dict[str, str], section: str, recipe: str, actor: str
) -> dict[str, Any]:
    """Create a dish (dish_id null) or save changes, as the dish form does."""
    kitchen = _kitchen()
    try:
        if dish_id is None:
            dish_id = await kitchen.create(_names(names), _section(section), recipe, actor)
            reset = False
        else:
            reset = await kitchen.update(
                int(dish_id), _names(names), _section(section), recipe, actor
            )
    except KitchenError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "reset": reset, "dish": await _dish(dish_id), "dishes": await dishes()}


async def confirm(
    dish_id: int, allergens: list[int], actor: str, expected_hash: str
) -> dict[str, Any]:
    """Confirm the allergens for the recipe the chef was looking at."""
    kitchen = _kitchen()
    try:
        await kitchen.confirm(int(dish_id), {int(n) for n in allergens}, actor, expected_hash)
    except KitchenError as exc:
        return {"ok": False, "error": str(exc), "stale": isinstance(exc, StaleRecipeError)}
    return {"ok": True, "dish": await _dish(int(dish_id)), "dishes": await dishes()}


async def menu(language: str = "en") -> dict[str, Any]:
    """The published menu: only dishes confirmed for their current recipe."""
    lang = parse_language(language)
    view = build_menu(await _kitchen().dishes(), lang, TITLE, _state.tz, demo=True)  # type: ignore[arg-type]
    texts = {key: view.text(key) for key in MENU_TEXT if key != "checked"}
    texts["checked"] = view.text("checked", date=view.last_checked)
    return {
        "language": lang.value,
        "title": view.title,
        "sections": [
            {
                "id": s.section.value,
                "title": s.title,
                "dishes": [
                    {
                        "id": d.id,
                        "name": d.name,
                        "allergens": list(d.allergens),
                        "translated": d.translated,
                    }
                    for d in s.dishes
                ],
            }
            for s in view.sections
        ],
        "legend": [
            {"number": line.number, "label": line.label, "detail": line.detail}
            for line in view.legend
        ],
        "hidden": view.hidden,
        "text": texts,
    }
