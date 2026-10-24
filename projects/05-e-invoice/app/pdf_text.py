"""Reads the text layer of a PDF and rebuilds lines and table cells from word positions.

pdfplumber's plain text joins table columns with single spaces ("8 Std. 85,00 19 % 680,00"),
which loses the column structure. Here a line is a set of words with the same baseline, and a
gap wider than half the font size between two words starts a new cell.
"""

import io
from dataclasses import dataclass, field

import pdfplumber
from pdfminer.pdfparser import PDFSyntaxError
from pdfplumber.utils.exceptions import PdfminerException

LINE_TOLERANCE = 2.5  # points: words whose tops differ less than this share a line
CELL_GAP_FACTOR = 0.5  # a gap > font size x this factor separates two cells
CELL_SEPARATOR = "    "  # how cells are joined in the plain text given to the LLM


class PdfError(ValueError):
    """The file is not a readable PDF, or it has no text layer (a scan)."""


@dataclass(frozen=True)
class Cell:
    x0: float
    x1: float
    text: str


@dataclass
class TextLine:
    page: int
    top: float
    cells: list[Cell] = field(default_factory=list)

    @property
    def text(self) -> str:
        return " ".join(cell.text for cell in self.cells)

    def __str__(self) -> str:
        return CELL_SEPARATOR.join(cell.text for cell in self.cells)


@dataclass
class PdfText:
    lines: list[TextLine]
    pages: int

    @property
    def plain(self) -> str:
        """Lines with cells separated by four spaces: compact, but keeps the columns."""
        return "\n".join(str(line) for line in self.lines)


def _group_lines(words: list[dict[str, object]], page: int) -> list[TextLine]:
    words = sorted(words, key=lambda w: (float(w["top"]), float(w["x0"])))  # type: ignore[arg-type]
    rows: list[list[dict[str, object]]] = []
    for word in words:
        if rows and abs(float(word["top"]) - float(rows[-1][0]["top"])) <= LINE_TOLERANCE:  # type: ignore[arg-type]
            rows[-1].append(word)
        else:
            rows.append([word])

    lines = []
    for row in rows:
        row.sort(key=lambda w: float(w["x0"]))  # type: ignore[arg-type]
        line = TextLine(page=page, top=float(row[0]["top"]))  # type: ignore[arg-type]
        current: list[dict[str, object]] = []
        for word in row:
            if current:
                gap = float(word["x0"]) - float(current[-1]["x1"])  # type: ignore[arg-type]
                size = max(float(word["size"]), float(current[-1]["size"]))  # type: ignore[arg-type]
                if gap > size * CELL_GAP_FACTOR:
                    line.cells.append(_cell(current))
                    current = []
            current.append(word)
        line.cells.append(_cell(current))
        lines.append(line)
    return lines


def _cell(words: list[dict[str, object]]) -> Cell:
    return Cell(
        x0=float(words[0]["x0"]),  # type: ignore[arg-type]
        x1=float(words[-1]["x1"]),  # type: ignore[arg-type]
        text=" ".join(str(w["text"]) for w in words),
    )


def read_pdf(data: bytes, max_pages: int = 20) -> PdfText:
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            if len(pdf.pages) > max_pages:
                raise PdfError(f"the PDF has {len(pdf.pages)} pages, the limit is {max_pages}")
            lines: list[TextLine] = []
            for number, page in enumerate(pdf.pages, start=1):
                words = page.extract_words(x_tolerance=1.5, extra_attrs=["size"])
                lines.extend(_group_lines(words, number))
            pages = len(pdf.pages)
    except (PdfminerException, PDFSyntaxError) as exc:
        raise PdfError("the file is not a readable PDF") from exc
    if not any(line.text.strip() for line in lines):
        raise PdfError("the PDF has no text layer (a scanned image?); OCR is not supported")
    return PdfText(lines=lines, pages=pages)
