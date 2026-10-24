"""SQLite storage. A report is stored as its JSON export, plus a few columns for the list."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import aiosqlite

from app.models import CheckStatus, Explanation, ScanReport, ScanStatus

SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
    id         INTEGER PRIMARY KEY,
    start_url  TEXT NOT NULL,
    sample     TEXT,
    status     TEXT NOT NULL,
    created_at TEXT NOT NULL,
    pages      INTEGER NOT NULL DEFAULT 0,
    failed     INTEGER NOT NULL DEFAULT 0,
    warnings   INTEGER NOT NULL DEFAULT 0,
    data       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reports_created ON reports (created_at);
"""


@dataclass(frozen=True)
class ReportRow:
    id: int
    start_url: str
    sample: str | None
    status: ScanStatus
    created_at: datetime
    pages: int
    failed: int
    warnings: int


class Repository:
    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._db = conn

    @classmethod
    async def connect(cls, path: Path | str) -> "Repository":
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        conn = await aiosqlite.connect(path)
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.executescript(SCHEMA)
        await conn.commit()
        return cls(conn)

    async def close(self) -> None:
        await self._db.close()

    async def create(self, report: ScanReport) -> int:
        cur = await self._db.execute(
            "INSERT INTO reports (start_url, sample, status, created_at, data) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                report.start_url,
                report.sample,
                report.status.value,
                report.created_at.isoformat(),
                report.model_dump_json(),
            ),
        )
        await self._db.commit()
        assert cur.lastrowid is not None
        return cur.lastrowid

    async def save(self, report: ScanReport) -> None:
        if report.id is None:
            raise ValueError("report has no id, call create() first")
        checks = report.summary.checks
        await self._db.execute(
            "UPDATE reports SET status = ?, pages = ?, failed = ?, warnings = ?, data = ? "
            "WHERE id = ?",
            (
                report.status.value,
                report.summary.pages_requested,
                checks.get(CheckStatus.FAIL, 0),
                checks.get(CheckStatus.WARNING, 0),
                report.model_dump_json(),
                report.id,
            ),
        )
        await self._db.commit()

    async def set_progress(self, report_id: int, pages: int) -> None:
        await self._db.execute("UPDATE reports SET pages = ? WHERE id = ?", (pages, report_id))
        await self._db.commit()

    async def get(self, report_id: int) -> ScanReport | None:
        async with self._db.execute("SELECT data FROM reports WHERE id = ?", (report_id,)) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        report = ScanReport.model_validate_json(row["data"])
        report.id = report_id
        return report

    async def get_row(self, report_id: int) -> ReportRow | None:
        async with self._db.execute("SELECT * FROM reports WHERE id = ?", (report_id,)) as cur:
            row = await cur.fetchone()
        return _row(row) if row else None

    async def recent(self, limit: int = 20) -> list[ReportRow]:
        async with self._db.execute(
            "SELECT * FROM reports ORDER BY id DESC LIMIT ?", (limit,)
        ) as cur:
            return [_row(row) for row in await cur.fetchall()]

    async def latest_sample(self, sample: str) -> int | None:
        async with self._db.execute(
            "SELECT id FROM reports WHERE sample = ? AND status = ? ORDER BY id DESC LIMIT 1",
            (sample, ScanStatus.DONE.value),
        ) as cur:
            row = await cur.fetchone()
        return int(row["id"]) if row else None

    async def set_explanation(self, report_id: int, explanation: Explanation) -> None:
        report = await self.get(report_id)
        if report is None:
            raise KeyError(report_id)
        report.explanation = explanation
        await self.save(report)

    async def fail_interrupted(self) -> int:
        """Scans that were running when the process stopped will never finish."""
        async with self._db.execute(
            "SELECT id FROM reports WHERE status = ?", (ScanStatus.RUNNING.value,)
        ) as cur:
            ids = [row["id"] for row in await cur.fetchall()]
        for report_id in ids:
            report = await self.get(report_id)
            if report is not None:
                report.status = ScanStatus.FAILED
                report.error = "The scan was interrupted by a restart. Start it again."
                await self.save(report)
        return len(ids)


def _row(row: aiosqlite.Row) -> ReportRow:
    return ReportRow(
        id=row["id"],
        start_url=row["start_url"],
        sample=row["sample"],
        status=ScanStatus(row["status"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        pages=row["pages"],
        failed=row["failed"],
        warnings=row["warnings"],
    )
