"""Exports the PDF text layer of the bundled samples for the in-browser demo.

pdfplumber needs pdfminer and pypdfium2, which do not run in the browser (Pyodide). So the
words of every sample page are read here, with the real pdfplumber, and saved as JSON in
samples/text-layer/. The demo rebuilds lines and cells from them with
app.pdf_text.from_words() and runs everything after that (extraction, derivation, the rules,
the XML) live in the browser. tests/test_web_demo.py fails if a JSON file is out of date.

    uv run python scripts/export_text_layer.py
    uv run python scripts/export_text_layer.py --images ../../site/public/demos/e-invoice/pages

--images also renders page 1 of every sample as a small PNG preview for the demo page.
"""

import argparse
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.pdf_text import read_words  # noqa: E402

SAMPLES = ROOT / "samples"
OUT = SAMPLES / "text-layer"
# The word attributes app.pdf_text uses to rebuild lines and cells.
KEYS = ("text", "x0", "x1", "top", "size")


def export(pdf: Path) -> dict[str, object]:
    pages = read_words(pdf.read_bytes())
    return {
        "file": pdf.name,
        "source": "pdfplumber extract_words(x_tolerance=1.5, extra_attrs=['size'])",
        "pages": [[{key: word[key] for key in KEYS} for word in words] for words in pages],
    }


def render_preview(pdf: Path, target: Path, width_px: int) -> None:
    import pdfplumber

    with pdfplumber.open(pdf) as doc:
        page = doc.pages[0]
        image = page.to_image(resolution=72 * width_px / float(page.width)).original
    # A text page needs few colours: a 32-colour palette keeps the PNG small.
    small = image.convert("RGB").quantize(colors=32)
    buffer = io.BytesIO()
    small.save(buffer, format="PNG", optimize=True)
    target.write_bytes(buffer.getvalue())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--images", type=Path, help="also write page-1 PNG previews here")
    parser.add_argument("--width", type=int, default=560, help="preview width in pixels")
    args = parser.parse_args()

    OUT.mkdir(exist_ok=True)
    for pdf in sorted(SAMPLES.glob("*.pdf")):
        target = OUT / f"{pdf.stem}.json"
        text = json.dumps(export(pdf), ensure_ascii=False, separators=(",", ":"))
        target.write_text(text + "\n", encoding="utf-8", newline="\n")
        print(f"{target.relative_to(ROOT)}: {len(text) // 1024} KB")
        if args.images:
            args.images.mkdir(parents=True, exist_ok=True)
            preview = args.images / f"{pdf.stem}.png"
            render_preview(pdf, preview, args.width)
            print(f"{preview}: {preview.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
