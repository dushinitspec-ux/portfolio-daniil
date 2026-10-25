"""Text normalization shared by the index, the queries and the triage rules.

The knowledge base is in English; employees also write in German, Russian and Turkish.
Without an embedding model, matching across languages needs three cheap steps:

1. fold: lowercase and strip accents, so "Passwört", "PASSWORT" and "passwort" are one word,
   and the Turkish dotted/dotless i do not split words in two;
2. a light English stemmer, so "printers", "printing" and "print" meet;
3. a small glossary of IT words in DE/RU/TR, matched by stem ("druckauftrag" starts with
   "druck" -> print), plus a fallback that maps "laptopumu" (Turkish suffixes on an English
   word) to the known word "laptop".
"""

import re
import unicodedata
from collections.abc import Iterable

# Hyphenated words are kept together ("wi-fi"), split on everything else.
_WORD = re.compile(r"[^\W_]+(?:-[^\W_]+)*")
_LATIN = re.compile(r"^[a-z0-9]+$")


def fold(text: str) -> str:
    """Lowercase without accents: "Şifre" -> "sifre", "Gäste" -> "gaste", "ё" -> "е"."""
    # casefold() turns "İ" into "i" + a combining dot and "ß" into "ss"; NFKD then splits
    # the remaining accented letters, and the combining marks are dropped.
    text = unicodedata.normalize("NFKD", text.replace("ı", "i").replace("’", "'").casefold())
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def words(text: str) -> list[str]:
    """Folded words. "Wi-Fi" -> "wifi"; "WLAN-Passwort" -> "wlanpasswort", "wlan", "passwort"."""
    result: list[str] = []
    for match in _WORD.finditer(fold(text)):
        word = match.group()
        if "-" in word:
            parts = word.split("-")
            result.append("".join(parts))
            result.extend(part for part in parts if len(part) >= 3)
        else:
            result.append(word)
    return result


# Words that carry no topic, in the four languages. The tokenizer splits "wasn't" into
# "wasn" + "t", so the contractions are listed by their first part (see BUGFIX.md, bug 1);
# one-letter leftovers are dropped by length.
_STOPWORDS_TEXT = """
    a an and are as at be been but by can could did do does doing for from had has have
    how i if in into is it its just me my of on or our should so some than that the
    their them then there these they this to too us was we were what when where which who
    why will with would you your yours am get got not no any all also about please hi hello
    thanks thank still even
    don doesn didn isn wasn aren weren couldn wouldn won haven hasn ll ve re
    der die das den dem des ein eine einen einem einer und oder ist sind war habe hat haben
    ich du er sie es wir ihr mein meine meinen mir mich dich nicht kein keine wie was wo
    wann warum mit von zu im in am auf fur aus bei nach uber unter tun kann konnen muss
    bitte hallo danke
    и в во не что как я ты он она мы вы они мой моя мое мои меня мне у к с со на по из за
    от до о об для это этот эта то так же ли бы да нет или а но уже что-то чтобы почему
    где когда можно нужно надо пожалуйста привет спасибо делать
    ve veya bir bu su o ben sen biz siz onlar benim bana beni ne nasil neden nerede ne zaman
    icin ile da de mi mu ama ya lutfen merhaba tesekkurler yapmaliyim yapmali
"""
STOPWORDS = frozenset(fold(word) for word in _STOPWORDS_TEXT.split())

# English suffixes, longest first. A stem must keep at least 3 letters.
_SUFFIXES = ("ing", "ed", "es", "s")


def stem(word: str) -> str:
    """A very light English stemmer: printers/printing/printed -> print, files/file -> fil.

    Only plain Latin words are stemmed; other alphabets are left to the glossary.
    """
    if not _LATIN.match(word) or len(word) <= 3:
        return word
    for suffix in _SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            if suffix == "es" and not word.endswith(("ses", "xes", "zes", "ches", "shes")):
                suffix = "s"  # "files" -> "file", but "boxes" -> "box"
            if suffix == "s" and word.endswith(("ss", "us", "is")):
                break  # "access", "status", "this": not plurals
            word = word[: -len(suffix)]
            doubled = len(word) >= 4 and word[-1] == word[-2] and word[-1] not in "lsz"
            if suffix in ("ing", "ed") and doubled:
                word = word[:-1]  # "dropping" -> "drop", but "installed" -> "install"
            break
    if word.endswith("e") and len(word) > 3:
        word = word[:-1]  # "delete"/"deleted" -> "delet", "file"/"files" -> "fil"
    return word


# German, Russian and Turkish IT words -> English words used in the knowledge base.
# Keys are matched as prefixes of folded words, so a key is a stem: "печат" covers
# "печать", "печатает", "распечатать" is not covered (it does not start with it).
GLOSSARY_SOURCE: dict[str, str] = {
    # German
    "passwort": "password",
    "kennwort": "password",
    "drucker": "printer",
    "druck": "print",
    "warteschlange": "queue",
    "wlan": "wifi",
    "gast": "guest",
    "gaste": "guest",
    "besucher": "visitor",
    "netzwerk": "network",
    "konto": "account",
    "gesperrt": "locked",
    "sperr": "locked",
    "anmeld": "sign in",
    "vergessen": "forgot",
    "zurucksetz": "reset",
    "postfach": "mailbox",
    "abwesenheit": "automatic replies",
    "bildschirm": "monitor screen",
    "kamera": "camera",
    "mikrofon": "microphone",
    "besprechung": "meeting",
    "datei": "file",
    "geloscht": "deleted",
    "losch": "delete",
    "wiederherstell": "restore",
    "sicherung": "backup",
    "verloren": "lost",
    "gestohlen": "stolen",
    "handy": "phone",
    "telefon": "phone",
    "mitarbeiter": "employee",
    "installier": "install",
    "programm": "software",
    "verdachtig": "suspicious",
    "scann": "scan",
    "papier": "paper",
    "neu": "new",
    # Russian
    "пароль": "password",
    "парол": "password",
    "принтер": "printer",
    "печат": "print",
    "очеред": "queue",
    "вайфай": "wifi",
    "wifi": "wifi",
    "сеть": "network",
    "сети": "network",
    "гост": "guest",
    "интернет": "internet",
    "впн": "vpn",
    "дом": "home",
    "удаленн": "remote",
    "учетн": "account",
    "аккаунт": "account",
    "заблокир": "locked",
    "забыл": "forgot",
    "сброс": "reset",
    "почт": "email",
    "письм": "email",
    "ящик": "mailbox",
    "камер": "camera",
    "микрофон": "microphone",
    "звонок": "call",
    "встреч": "meeting",
    "файл": "file",
    "удалил": "deleted",
    "восстанов": "restore",
    "бэкап": "backup",
    "резервн": "backup",
    "потерял": "lost",
    "украл": "stolen",
    "телефон": "phone",
    "ноутбук": "laptop",
    "нов": "new",
    "сотрудник": "employee",
    "установ": "install",
    "программ": "software",
    "приложени": "app",
    "подозрит": "suspicious",
    "фишинг": "phishing",
    "скан": "scan",
    "настро": "set up",
    "подключ": "connect",
    "монитор": "monitor",
    "экран": "screen",
    # Turkish
    "sifre": "password",
    "parola": "password",
    "yazici": "printer",
    "yazdir": "print",
    "kuyruk": "queue",
    "kablosuz": "wifi",
    "misafir": "guest",
    "hesap": "account",
    "kilitlen": "locked",
    "unuttum": "forgot",
    "sifirla": "reset",
    "eposta": "email",
    "posta": "email",
    "kutusu": "mailbox",
    "toplanti": "meeting",
    "dosya": "file",
    "sil": "deleted",
    "geri": "restore",
    "yedek": "backup",
    "kaybet": "lost",
    "kayip": "lost",
    "calindi": "stolen",
    "dizustu": "laptop",
    "yeni": "new",
    "calisan": "employee",
    "kur": "install",
    "yukle": "install",
    "uygulama": "app",
    "supheli": "suspicious",
    "oltalama": "phishing",
    "baglan": "connect",
    "ekran": "screen",
}


def _build_glossary(source: dict[str, str]) -> dict[str, tuple[str, ...]]:
    return {
        fold(key): tuple(stem(w) for w in words(value) if w not in STOPWORDS)
        for key, value in source.items()
    }


GLOSSARY = _build_glossary(GLOSSARY_SOURCE)
# Longest keys first, so "passwort" wins over a shorter key that is also a prefix.
_GLOSSARY_KEYS = sorted(GLOSSARY, key=len, reverse=True)

# Unknown words at least this long may be matched to a known word they start with.
MIN_PREFIX_MATCH = 5


def translate(word: str) -> tuple[str, ...]:
    """English stems for a folded non-English word, or () if the glossary has none."""
    for key in _GLOSSARY_KEYS:
        if word.startswith(key):
            return GLOSSARY[key]
    return ()


# How people write in a chat -> how the knowledge base is written. Each user word keeps its
# own meaning and gets the knowledge-base word as an alternative ("log in" -> sign in).
SYNONYMS_SOURCE: dict[str, str] = {
    "log": "sign",
    "login": "sign",
    "logon": "sign",
    "internet": "wifi",
    "drop": "disconnect",
    "pc": "laptop",
    "computer": "laptop",
    "notebook": "laptop",
    "mail": "email",
    "pw": "password",
    "pwd": "password",
    "2fa": "mfa",
    "twofactor": "mfa",
    "ooo": "automatic replies",
}
SYNONYMS: dict[str, tuple[str, ...]] = {
    stem(fold(key)): tuple(stem(w) for w in words(value) if w not in STOPWORDS)
    for key, value in SYNONYMS_SOURCE.items()
}


def analyze_groups(
    text: str,
    *,
    stemming: bool = True,
    glossary: bool = True,
    synonyms: bool = True,
    vocabulary: Iterable[str] = (),
) -> list[tuple[str, ...]]:
    """One group of alternative terms per meaningful word of `text`.

    `vocabulary` is the set of indexed terms. With `glossary` on, a word that is not in it
    is looked up in the glossary, and then matched to the longest indexed term it starts
    with ("laptopumu" -> "laptop"), so Turkish and Russian endings on English words do not
    hide them. With `synonyms` on, chat words also get their knowledge-base word
    ("log" -> "sign").
    """
    vocab = vocabulary if isinstance(vocabulary, (set, frozenset)) else set(vocabulary)
    groups: list[tuple[str, ...]] = []
    for word in words(text):
        if len(word) < 2 or word in STOPWORDS:
            continue
        term = stem(word) if stemming else word
        extra = SYNONYMS.get(term, ()) if synonyms else ()
        if not glossary or not vocab or term in vocab or extra:
            groups.append((term, *extra))
        elif translated := translate(word):
            groups.append(translated)
        else:
            groups.append((_longest_known_prefix(word, vocab) or term,))
    return groups


def analyze(
    text: str,
    *,
    stemming: bool = True,
    glossary: bool = True,
    synonyms: bool = True,
    vocabulary: Iterable[str] = (),
) -> list[str]:
    """Words of `text` ready for BM25: folded, stopwords removed, stemmed, translated."""
    groups = analyze_groups(
        text, stemming=stemming, glossary=glossary, synonyms=synonyms, vocabulary=vocabulary
    )
    return [term for group in groups for term in group]


def _longest_known_prefix(word: str, vocabulary: set[str] | frozenset[str]) -> str | None:
    for end in range(len(word) - 1, MIN_PREFIX_MATCH - 1, -1):
        if word[:end] in vocabulary:
            return word[:end]
    return None
