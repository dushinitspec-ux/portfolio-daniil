import json
from pathlib import Path

import pytest

from app.config import get_settings
from app.main import build_parser, main


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)  # no .env from the project folder
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "cli.db"))
    monkeypatch.setenv("REQUEST_DELAY_S", "0")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_scan_sample_writes_json_and_html(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out_json, out_html = tmp_path / "r.json", tmp_path / "r.html"

    code = main(["scan", "--sample", "broken", "--json", str(out_json), "--html", str(out_html),
                 "--explain"])  # fmt: skip

    assert code == 0
    printed = capsys.readouterr().out
    assert "FAIL  1.1.1  Non-text Content (A)  8 issues on 3 pages" in printed
    assert "Checks: 10 failed, 7 warnings, 0 passed, 0 not applicable." in printed
    assert "For the shop owner (fixed texts)" in printed
    data = json.loads(out_json.read_text(encoding="utf-8"))
    assert data["summary"]["pages_analysed"] == 4
    assert "<!doctype html>" in out_html.read_text(encoding="utf-8")


def test_scan_refuses_a_private_address(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["scan", "http://127.0.0.1/"]) == 2
    assert "private or local address" in capsys.readouterr().err


def test_parser_accepts_demo_before_or_after_the_command() -> None:
    parser = build_parser()
    assert parser.parse_args(["--demo"]).demo is True
    assert parser.parse_args(["serve", "--demo"]).demo is True
    args = parser.parse_args(["scan", "https://example.com", "--max-pages", "10"])
    assert (args.url, args.max_pages, getattr(args, "demo", False)) == (
        "https://example.com",
        10,
        False,
    )
    with pytest.raises(SystemExit):
        parser.parse_args(["scan"])  # needs a URL or --sample
