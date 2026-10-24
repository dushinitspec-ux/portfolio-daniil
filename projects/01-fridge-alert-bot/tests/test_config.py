from pathlib import Path

import pytest

from app.config import Settings


def test_empty_values_in_env_file_mean_not_set(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("BOT_TOKEN=\nALERT_CHAT_ID=\nALLOWED_CHAT_IDS=\n", encoding="utf-8")
    settings = Settings(_env_file=env)  # type: ignore[call-arg]
    assert settings.alert_chat_id is None
    assert settings.allowed_chat_ids == []
    assert settings.telegram_enabled is False


def test_comma_separated_chat_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALERT_CHAT_ID", "-1001")
    monkeypatch.setenv("ALLOWED_CHAT_IDS", "42, 43")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.command_chat_ids == {-1001, 42, 43}


def test_unknown_timezone_is_rejected() -> None:
    with pytest.raises(ValueError):
        Settings(_env_file=None, timezone="Mars/Olympus")  # type: ignore[call-arg]
