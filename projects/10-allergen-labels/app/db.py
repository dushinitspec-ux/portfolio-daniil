"""SQLite storage: dishes, the confirmation log, the event log and cached AI suggestions.

Confirmations and events are append-only: triggers make SQLite refuse UPDATE and DELETE on
them, so the log of who confirmed what cannot be rewritten through the app.

Timestamps are ISO 8601 strings in UTC.
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import aiosqlite

from app.i18n import Language

SCHEMA = """
CREATE TABLE IF NOT EXISTS dishes (
    id              INTEGER PRIMARY KEY,
    section         TEXT NOT NULL,
    position        INTEGER NOT NULL DEFAULT 0,
    name_en         TEXT NOT NULL,
    name_ru         TEXT NOT NULL DEFAULT '',
    name_tr         TEXT NOT NULL DEFAULT '',
    name_de         TEXT NOT NULL DEFAULT '',
    recipe          TEXT NOT NULL,
    recipe_hash     TEXT NOT NULL,
    -- The confirmation that is valid for the current recipe; NULL = not confirmed.
    confirmation_id INTEGER REFERENCES confirmations(id),
    archived        INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    updated_by      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS confirmations (
    id           INTEGER PRIMARY KEY,
    dish_id      INTEGER NOT NULL REFERENCES dishes(id),
    recipe_hash  TEXT NOT NULL,
    recipe       TEXT NOT NULL,
    allergens    TEXT NOT NULL,
    confirmed_by TEXT NOT NULL,
    confirmed_at TEXT NOT NULL,
    note         TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_confirmations_dish ON confirmations (dish_id, id);

CREATE TABLE IF NOT EXISTS events (
    id      INTEGER PRIMARY KEY,
    dish_id INTEGER,
    at      TEXT NOT NULL,
    actor   TEXT NOT NULL,
    action  TEXT NOT NULL,
    detail  TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_events_dish ON events (dish_id, id);

CREATE TABLE IF NOT EXISTS ai_suggestions (
    key        TEXT PRIMARY KEY,
    ingredient TEXT NOT NULL,
    allergens  TEXT NOT NULL,
    reason     TEXT NOT NULL,
    model      TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS confirmations_no_update BEFORE UPDATE ON confirmations
BEGIN SELECT RAISE(ABORT, 'confirmations are append-only'); END;
CREATE TRIGGER IF NOT EXISTS confirmations_no_delete BEFORE DELETE ON confirmations
BEGIN SELECT RAISE(ABORT, 'confirmations are append-only'); END;
CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
"""


def to_db(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds")


def from_db(value: str) -> datetime:
    return datetime.fromisoformat(value)


@dataclass(frozen=True)
class DishRow:
    id: int
    section: str
    position: int
    names: dict[Language, str]
    recipe: str
    recipe_hash: str
    confirmation_id: int | None
    archived: bool
    created_at: datetime
    updated_at: datetime
    updated_by: str


@dataclass(frozen=True)
class Confirmation:
    id: int
    dish_id: int
    recipe_hash: str
    recipe: str
    allergens: tuple[int, ...]
    confirmed_by: str
    confirmed_at: datetime
    note: str


@dataclass(frozen=True)
class Event:
    dish_id: int | None
    at: datetime
    actor: str
    action: str
    detail: str


@dataclass(frozen=True)
class CachedSuggestion:
    ingredient: str
    allergens: tuple[str, ...]
    reason: str
    model: str


def _dish(row: aiosqlite.Row) -> DishRow:
    return DishRow(
        id=row["id"],
        section=row["section"],
        position=row["position"],
        names={lang: row[f"name_{lang.value}"] for lang in Language},
        recipe=row["recipe"],
        recipe_hash=row["recipe_hash"],
        confirmation_id=row["confirmation_id"],
        archived=bool(row["archived"]),
        created_at=from_db(row["created_at"]),
        updated_at=from_db(row["updated_at"]),
        updated_by=row["updated_by"],
    )


def _confirmation(row: aiosqlite.Row) -> Confirmation:
    return Confirmation(
        id=row["id"],
        dish_id=row["dish_id"],
        recipe_hash=row["recipe_hash"],
        recipe=row["recipe"],
        allergens=tuple(json.loads(row["allergens"])),
        confirmed_by=row["confirmed_by"],
        confirmed_at=from_db(row["confirmed_at"]),
        note=row["note"],
    )


class Repository:
    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._db = conn

    @classmethod
    async def connect(cls, path: Path | str) -> "Repository":
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        conn = await aiosqlite.connect(path)
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")
        if str(path) != ":memory:":
            await conn.execute("PRAGMA journal_mode=WAL")
        await conn.executescript(SCHEMA)
        await conn.commit()
        return cls(conn)

    async def close(self) -> None:
        await self._db.close()

    async def commit(self) -> None:
        await self._db.commit()

    async def rollback(self) -> None:
        await self._db.rollback()

    @property
    def connection(self) -> aiosqlite.Connection:
        return self._db

    # Dishes

    async def add_dish(
        self,
        section: str,
        names: dict[Language, str],
        recipe: str,
        recipe_hash: str,
        actor: str,
        at: datetime,
    ) -> int:
        async with self._db.execute("SELECT COALESCE(MAX(position), 0) + 1 FROM dishes") as cur:
            row = await cur.fetchone()
        position = row[0] if row else 1
        cur = await self._db.execute(
            """
            INSERT INTO dishes (section, position, name_en, name_ru, name_tr, name_de, recipe,
                                recipe_hash, created_at, updated_at, updated_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                section,
                position,
                names.get(Language.EN, ""),
                names.get(Language.RU, ""),
                names.get(Language.TR, ""),
                names.get(Language.DE, ""),
                recipe,
                recipe_hash,
                to_db(at),
                to_db(at),
                actor,
            ),
        )
        assert cur.lastrowid is not None
        return cur.lastrowid

    async def update_dish(
        self,
        dish_id: int,
        section: str,
        names: dict[Language, str],
        recipe: str,
        recipe_hash: str,
        actor: str,
        at: datetime,
        reset_confirmation: bool,
    ) -> None:
        await self._db.execute(
            f"""
            UPDATE dishes SET section = ?, name_en = ?, name_ru = ?, name_tr = ?, name_de = ?,
                   recipe = ?, recipe_hash = ?, updated_at = ?, updated_by = ?
                   {", confirmation_id = NULL" if reset_confirmation else ""}
             WHERE id = ?
            """,
            (
                section,
                names.get(Language.EN, ""),
                names.get(Language.RU, ""),
                names.get(Language.TR, ""),
                names.get(Language.DE, ""),
                recipe,
                recipe_hash,
                to_db(at),
                actor,
                dish_id,
            ),
        )

    async def set_archived(self, dish_id: int, archived: bool) -> None:
        await self._db.execute(
            "UPDATE dishes SET archived = ? WHERE id = ?", (int(archived), dish_id)
        )

    async def get_dish(self, dish_id: int) -> DishRow | None:
        async with self._db.execute("SELECT * FROM dishes WHERE id = ?", (dish_id,)) as cur:
            row = await cur.fetchone()
        return _dish(row) if row else None

    async def list_dishes(self) -> list[DishRow]:
        async with self._db.execute("SELECT * FROM dishes ORDER BY position, id") as cur:
            return [_dish(row) for row in await cur.fetchall()]

    async def count_dishes(self) -> int:
        async with self._db.execute("SELECT COUNT(*) FROM dishes") as cur:
            row = await cur.fetchone()
        return int(row[0]) if row else 0

    # Confirmations (append-only)

    async def add_confirmation(
        self,
        dish_id: int,
        recipe_hash: str,
        recipe: str,
        allergens: list[int],
        actor: str,
        at: datetime,
        note: str = "",
    ) -> int:
        cur = await self._db.execute(
            """
            INSERT INTO confirmations (dish_id, recipe_hash, recipe, allergens, confirmed_by,
                                       confirmed_at, note)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (dish_id, recipe_hash, recipe, json.dumps(sorted(allergens)), actor, to_db(at), note),
        )
        assert cur.lastrowid is not None
        confirmation_id = cur.lastrowid
        await self._db.execute(
            "UPDATE dishes SET confirmation_id = ? WHERE id = ?", (confirmation_id, dish_id)
        )
        return confirmation_id

    async def get_confirmation(self, confirmation_id: int) -> Confirmation | None:
        async with self._db.execute(
            "SELECT * FROM confirmations WHERE id = ?", (confirmation_id,)
        ) as cur:
            row = await cur.fetchone()
        return _confirmation(row) if row else None

    async def confirmations(self, dish_id: int) -> list[Confirmation]:
        async with self._db.execute(
            "SELECT * FROM confirmations WHERE dish_id = ? ORDER BY id DESC", (dish_id,)
        ) as cur:
            return [_confirmation(row) for row in await cur.fetchall()]

    async def all_confirmations(self) -> dict[int, Confirmation]:
        async with self._db.execute("SELECT * FROM confirmations") as cur:
            return {row["id"]: _confirmation(row) for row in await cur.fetchall()}

    # Events (append-only)

    async def add_event(
        self, dish_id: int | None, actor: str, action: str, detail: str, at: datetime
    ) -> None:
        await self._db.execute(
            "INSERT INTO events (dish_id, at, actor, action, detail) VALUES (?, ?, ?, ?, ?)",
            (dish_id, to_db(at), actor, action, detail),
        )

    async def events(self, dish_id: int, limit: int = 50) -> list[Event]:
        async with self._db.execute(
            "SELECT * FROM events WHERE dish_id = ? ORDER BY id DESC LIMIT ?", (dish_id, limit)
        ) as cur:
            rows = await cur.fetchall()
        return [
            Event(r["dish_id"], from_db(r["at"]), r["actor"], r["action"], r["detail"])
            for r in rows
        ]

    # AI suggestions cache

    async def get_suggestions(self, keys: list[str]) -> dict[str, CachedSuggestion]:
        if not keys:
            return {}
        marks = ",".join("?" * len(keys))
        async with self._db.execute(
            f"SELECT * FROM ai_suggestions WHERE key IN ({marks})", keys
        ) as cur:
            rows = await cur.fetchall()
        return {
            r["key"]: CachedSuggestion(
                r["ingredient"], tuple(json.loads(r["allergens"])), r["reason"], r["model"]
            )
            for r in rows
        }

    async def save_suggestion(
        self, key: str, ingredient: str, allergens: list[str], reason: str, model: str, at: datetime
    ) -> None:
        await self._db.execute(
            """
            INSERT OR REPLACE INTO ai_suggestions (key, ingredient, allergens, reason, model,
                                                   created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (key, ingredient, json.dumps(allergens), reason, model, to_db(at)),
        )
