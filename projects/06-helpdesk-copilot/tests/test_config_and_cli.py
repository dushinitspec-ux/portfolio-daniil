import pytest
from pydantic import ValidationError

from app.config import Settings
from app.main import ask_once, main


def test_demo_can_be_switched_on_with_demo_or_demo_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEMO", "1")
    assert Settings(_env_file=None).demo_mode  # type: ignore[call-arg]
    monkeypatch.delenv("DEMO")
    monkeypatch.setenv("DEMO_MODE", "true")
    assert Settings(_env_file=None).demo_mode  # type: ignore[call-arg]


def test_empty_values_in_env_mean_not_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IT_CHAT_ID", "")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.it_chat_id is None
    assert settings.anthropic_model == "claude-opus-5-5"
    assert settings.port == 8106


def test_unknown_timezone_is_rejected() -> None:
    with pytest.raises(ValidationError, match="unknown timezone"):
        Settings(_env_file=None, timezone="Mars/Olympus")  # type: ignore[call-arg]


def test_without_demo_an_api_key_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.main.get_settings", lambda: Settings(_env_file=None))  # type: ignore[call-arg]
    with pytest.raises(SystemExit, match="ANTHROPIC_API_KEY is not set"):
        main(["ask", "How do I connect to the VPN?"])


async def test_ask_in_the_terminal(settings: Settings) -> None:
    output = await ask_once(settings, "Wie lautet das WLAN-Passwort für Gäste?")
    assert "[1] Guest Wi-Fi › Get the guest Wi-Fi password" in output
    output = await ask_once(settings, "The coffee machine is leaking")
    assert "Ticket: P3 hardware" in output
