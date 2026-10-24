import pytest

from app.language import Language, detect_language, resolve_language


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Во сколько завтрак?", Language.RU),
        ("Где бассейн", Language.RU),
        ("Havuz saat kaçta açılıyor?", Language.TR),
        ("Havuz ne zaman acik", Language.TR),  # typed without Turkish letters
        ("İyi akşamlar, oda servisi var mı?", Language.TR),
        ("Wann gibt es Frühstück?", Language.DE),
        ("Wo ist der Pool?", Language.DE),  # no umlauts
        ("Straße zum Strand", Language.DE),
        ("Where is the pool?", Language.EN),
        ("Can I have a late check-out?", Language.EN),
    ],
)
def test_detects_language(text: str, expected: Language) -> None:
    assert detect_language(text) is expected


@pytest.mark.parametrize("text", ["ok", "Wi-Fi?", "12:00", "👍", ""])
def test_no_signal_returns_none(text: str) -> None:
    assert detect_language(text) is None


def test_short_reply_keeps_conversation_language() -> None:
    assert resolve_language("ok", Language.RU, "en") is Language.RU


def test_falls_back_to_telegram_app_language() -> None:
    assert resolve_language("Wi-Fi?", None, "de-AT") is Language.DE


def test_unsupported_app_language_falls_back_to_english() -> None:
    assert resolve_language("👍", None, "fr") is Language.EN
    assert resolve_language("👍", None, None) is Language.EN


def test_text_wins_over_previous_language() -> None:
    assert resolve_language("Where is the spa?", Language.RU, "ru") is Language.EN
