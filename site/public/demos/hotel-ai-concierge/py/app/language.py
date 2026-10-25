"""Detect whether a guest writes in English, Russian, Turkish or German.

A small rule-based detector is enough for four languages with very different
alphabets and function words, and it works offline. Short messages like "ok" or
"Wi-Fi?" carry no signal; for those we keep the language of the conversation,
then fall back to the language of the guest's Telegram app.
"""

import re
from enum import StrEnum


class Language(StrEnum):
    EN = "en"
    RU = "ru"
    TR = "tr"
    DE = "de"

    @property
    def english_name(self) -> str:
        return _NAMES[self]


_NAMES = {
    Language.EN: "English",
    Language.RU: "Russian",
    Language.TR: "Turkish",
    Language.DE: "German",
}

# Letters that exist in only one of the four languages.
_TURKISH_LETTERS = set("ğĞıİşŞçÇ")
_GERMAN_LETTERS = set("äÄß")


def _words(text: str) -> frozenset[str]:
    return frozenset(text.split())


# Frequent words that are not shared between the Latin-script languages.
_STOPWORDS = {
    Language.EN: _words(
        "the is are what when where how do does can could you your my to of for there time "
        "please have has i it and with hello hi thanks thank room open any"
    ),
    Language.DE: _words(
        "der die das ist sind wann wo wie ich und ein eine gibt es haben bitte mit für kann "
        "nicht zimmer frühstück hallo danke guten uhr einen mein meine auch"
    ),
    Language.TR: _words(
        "ne zaman nerede nerde nasıl var mı mi mu mü ve bir bu saat kaç kahvaltı oda odada "
        "havuz lütfen için ben merhaba otel yok teşekkürler teşekkür ederim acaba"
    ),
}

_WORD = re.compile(r"[^\W\d_]+")


def detect_language(text: str) -> Language | None:
    """Return the language of `text`, or None when the text gives no clear signal."""
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return None
    cyrillic = sum("Ѐ" <= ch <= "ӿ" for ch in letters)
    if cyrillic / len(letters) > 0.3:
        return Language.RU

    scores = dict.fromkeys(_STOPWORDS, 0)
    scores[Language.TR] += 3 * sum(ch in _TURKISH_LETTERS for ch in text)
    scores[Language.DE] += 3 * sum(ch in _GERMAN_LETTERS for ch in text)
    # casefold() would turn Turkish "İ" into "i̇"; lower() is fine for the word lists.
    for word in _WORD.findall(text.lower()):
        for language, words in _STOPWORDS.items():
            if word in words:
                scores[language] += 1

    best = max(scores, key=lambda lang: scores[lang])
    return best if scores[best] > 0 else None


def resolve_language(text: str, previous: Language | None, telegram_code: str | None) -> Language:
    """Language to answer in: the text itself, then the conversation, then the app."""
    detected = detect_language(text)
    if detected:
        return detected
    if previous:
        return previous
    if telegram_code:
        try:
            return Language(telegram_code.split("-")[0].lower())  # "de-AT" -> "de"
        except ValueError:
            pass
    return Language.EN
