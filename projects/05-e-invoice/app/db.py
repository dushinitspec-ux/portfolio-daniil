"""SQLite history of processed invoices: what came in, what came out, which rules failed."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Self

import aiosqlite

from app.model import Extraction
from app.pipeline import Conversion

SCHEMA = """
CREATE TABLE IF NOT EXISTS invoices (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at    TEXT    NOT NULL,
    filename      TEXT    NOT NULL,
    extractor     TEXT    NOT NULL,
    number        TEXT    NOT NULL,
    seller        TEXT    NOT NULL,
    currency      TEXT    NOT NULL,
    total         TEXT,               -- Decimal as text, never a float
    status        TEXT    NOT NULL,   -- 'valid' or 'invalid'
    failed_rules  TEXT    NOT NULL,   -- JSON list of rule IDs (fatal and warning)
    extraction    TEXT    NOT NULL,   -- JSON of the typed invoice and notes
    xml           BLOB    NOT NULL,
    pdf           BLOB    NOT NULL
);
CREATE INDEX IF NOT EXISTS invoices_created ON invoices (created_at);
"""


@dataclass(frozen=True)
class HistoryRow:
    id: int
    created_at: datetime
    filename: str
    extractor: str
    number: str
    seller: str
    currency: str
    total: Decimal | None
    valid: bool
    failed_rules: list[str]


@dataclass(frozen=True)
class StoredInvoice:
    row: HistoryRow
    extraction: Extraction
    xml: bytes
    pdf: bytes


_COLUMNS = (
    "id, created_at, filename, extractor, number, seller, currency, total, status, failed_rules"
)


def _row(values: tuple[object, ...]) -> HistoryRow:
    (id_, created, filename, extractor, number, seller, currency, total, status, failed) = values
    return HistoryRow(
        id=int(id_),  # type: ignore[call-overload]
        created_at=datetime.fromisoformat(str(created)),
        filename=str(filename),
        extractor=str(extractor),
        number=str(number),
        seller=str(seller),
        currency=str(currency),
        total=Decimal(str(total)) if total is not None else None,
        valid=status == "valid",
        failed_rules=json.loads(str(failed)),
    )


class Repository:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    @classmethod
    async def connect(cls, path: Path | str) -> Self:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        db = await aiosqlite.connect(path)
        await db.executescript(SCHEMA)
        await db.commit()
        return cls(db)

    async def close(self) -> None:
        await self._db.close()

    @staticmethod
    def _values(conversion: Conversion) -> tuple[object, ...]:
        invoice = conversion.invoice
        total = invoice.totals.payable
        failed = [r.id for r in conversion.report.errors + conversion.report.warnings]
        return (
            conversion.extraction.extractor,
            invoice.number,
            invoice.seller.name,
            invoice.currency,
            None if total is None else f"{total:f}",
            "valid" if conversion.valid else "invalid",
            json.dumps(failed),
            conversion.extraction.model_dump_json(),
            conversion.xml,
        )

    async def add(self, conversion: Conversion, pdf: bytes, now: datetime | None = None) -> int:
        created = (now or datetime.now(UTC)).isoformat(timespec="seconds")
        cursor = await self._db.execute(
            "INSERT INTO invoices (created_at, filename, extractor, number, seller, currency, "
            "total, status, failed_rules, extraction, xml, pdf) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (created, conversion.filename, *self._values(conversion), pdf),
        )
        await self._db.commit()
        assert cursor.lastrowid is not None
        return cursor.lastrowid

    async def replace(self, invoice_id: int, conversion: Conversion) -> None:
        """Store a re-run (e.g. with the buyer's e-invoice address added) under the same id."""
        await self._db.execute(
            "UPDATE invoices SET extractor = ?, number = ?, seller = ?, currency = ?, total = ?, "
            "status = ?, failed_rules = ?, extraction = ?, xml = ? WHERE id = ?",
            (*self._values(conversion), invoice_id),
        )
        await self._db.commit()

    async def recent(self, limit: int = 20) -> list[HistoryRow]:
        cursor = await self._db.execute(
            f"SELECT {_COLUMNS} FROM invoices ORDER BY id DESC LIMIT ?", (limit,)
        )
        return [_row(tuple(values)) for values in await cursor.fetchall()]

    async def get(self, invoice_id: int) -> StoredInvoice | None:
        cursor = await self._db.execute(
            f"SELECT {_COLUMNS}, extraction, xml, pdf FROM invoices WHERE id = ?", (invoice_id,)
        )
        values = await cursor.fetchone()
        if values is None:
            return None
        values = tuple(values)
        return StoredInvoice(
            row=_row(values[:10]),
            extraction=Extraction.model_validate_json(str(values[10])),
            xml=bytes(values[11]),
            pdf=bytes(values[12]),
        )
