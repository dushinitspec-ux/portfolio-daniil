"""Measure the dictionary on a labelled sample: `uv run python -m app.evaluate`.

The sample (tests/fixtures/labelled_sample.csv) is ingredient lines as a kitchen writes them,
in four languages, each labelled with the Annex II groups it contains. I wrote the labels
myself; they are not an official data set.

What counts:
- found: an expected allergen is pre-selected for the chef (certain or "possible").
- silent miss: an expected allergen is not pre-selected AND the line is not flagged for a
  check. This is the dangerous case and should be zero.
- flagged miss: not pre-selected, but the line is flagged, so a person looks at it.
- extra: an allergen pre-selected that the label does not list (the chef unticks it).
"""

import csv
import io
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from app.matcher import Status, analyse

SAMPLE = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "labelled_sample.csv"


@dataclass(frozen=True)
class Row:
    language: str
    ingredient: str
    expected: frozenset[int]


@dataclass
class Report:
    lines: int = 0
    expected: int = 0
    found: int = 0
    silent_misses: int = 0
    flagged_misses: int = 0
    extra: int = 0
    flagged_lines: int = 0
    clean_lines: int = 0  # lines with no allergen expected and none pre-selected
    no_allergen_lines: int = 0
    details: list[str] | None = None


def load(path: Path = SAMPLE) -> list[Row]:
    with path.open(encoding="utf-8", newline="") as handle:
        return [
            Row(
                r["language"],
                r["ingredient"],
                frozenset(int(n) for n in r["expected"].split()),
            )
            for r in csv.DictReader(handle)
        ]


def evaluate(rows: list[Row]) -> tuple[Report, Counter[str]]:
    report = Report(details=[])
    per_language: Counter[str] = Counter()
    for row in rows:
        result = analyse(row.ingredient)
        got = result.allergens
        flagged = any(i.status is Status.CHECK for i in result.items)
        report.lines += 1
        report.expected += len(row.expected)
        report.found += len(row.expected & got)
        report.extra += len(got - row.expected)
        report.flagged_lines += flagged
        if not row.expected:
            report.no_allergen_lines += 1
            report.clean_lines += not got
        for missing in sorted(row.expected - got):
            if flagged:
                report.flagged_misses += 1
                kind = "flagged miss"
            else:
                report.silent_misses += 1
                per_language[row.language] += 1
                kind = "SILENT MISS"
            assert report.details is not None
            report.details.append(f"{kind}: [{row.language}] {row.ingredient!r} -> {missing}")
        for extra in sorted(got - row.expected):
            assert report.details is not None
            report.details.append(f"extra: [{row.language}] {row.ingredient!r} -> {extra}")
    return report, per_language


def main() -> None:
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    rows = load()
    report, _ = evaluate(rows)
    print(f"Lines: {report.lines} ({', '.join(sorted({r.language for r in rows}))})")
    print(f"Expected allergens: {report.expected}")
    print(f"Pre-selected for the chef: {report.found} ({report.found / report.expected:.1%})")
    print(f"Silent misses: {report.silent_misses}")
    print(f"Missed but flagged for a check: {report.flagged_misses}")
    print(f"Extra allergens pre-selected: {report.extra}")
    print(f"Lines flagged for a check: {report.flagged_lines}")
    print(
        f"Lines with no allergen expected and none pre-selected: "
        f"{report.clean_lines} of {report.no_allergen_lines}"
    )
    for line in report.details or []:
        print("  " + line)


if __name__ == "__main__":
    main()
