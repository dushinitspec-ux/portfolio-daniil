import os
import subprocess
import sys

import pytest

from app.cli import main, mask_command
from app.guard import Guard
from tests.conftest import CARD, EMAIL, IBAN, ROOT


def test_mask_prints_the_masked_text(guard: Guard, capsys: pytest.CaptureFixture[str]) -> None:
    code = mask_command(guard, f"IBAN {IBAN}, mail {EMAIL}")
    out, err = capsys.readouterr()
    assert code == 0
    assert out == "IBAN <IBAN_1>, mail <EMAIL_1>\n"
    assert "EMAIL: 1 found, mask" in err
    assert IBAN not in out + err and EMAIL not in out + err


def test_mask_blocked_exits_with_2(guard: Guard, capsys: pytest.CaptureFixture[str]) -> None:
    code = mask_command(guard, f"card {CARD}")
    out, err = capsys.readouterr()
    assert code == 2
    assert out == ""
    assert "blocked by policy (CARD)" in err


def test_main_mask_command(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["mask", f"Doğum tarihi: 14.03.1985, mail {EMAIL}"]) == 0
    assert capsys.readouterr().out == "Doğum tarihi: <DATE_OF_BIRTH_1>, mail <EMAIL_1>\n"


def test_piped_output_is_utf8_whatever_the_console_code_page() -> None:
    # BUGFIX.md, bug 1: on a Russian Windows, piped stdout defaulted to cp1251 and the
    # Turkish "ğ" was lost. Run the real CLI with its output piped, as in the bug report.
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONIOENCODING", "PYTHONUTF8")}
    done = subprocess.run(
        [sys.executable, "-m", "app", "mask", "Doğum tarihi: 14.03.1985"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        check=True,
    )
    assert done.stdout.decode("utf-8").strip() == "Doğum tarihi: <DATE_OF_BIRTH_1>"


def test_main_reports_a_broken_config(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("POLICY_FILE", "does-not-exist.yaml")
    assert main(["mask", "hello"]) == 1
    assert "policy file not found" in capsys.readouterr().err
