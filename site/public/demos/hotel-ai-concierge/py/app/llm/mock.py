"""Offline stand-in for an LLM, so the demo runs with no API key and no internet.

It picks the knowledge-base section whose keywords appear in the question
(in any of the four languages) and quotes it. It cannot translate, so the quoted
text stays in English. Questions with no matching section are escalated, which is
exactly the behaviour the real prompt asks for.
"""

import re

from app.knowledge import parse_sections
from app.language import Language
from app.llm.base import ConciergeAnswer

# Keyword stems per topic. A topic matches a section when its key is in the title.
TOPIC_KEYWORDS: dict[str, list[str]] = {
    "check-in": ["check-in", "check in", "заезд", "заселен", "giriş", "einchecken", "anreise"],
    "check-out": [
        "check-out",
        "checkout",
        "check out",
        "выезд",
        "выселен",
        "çıkış",
        "auschecken",
        "abreise",
        "luggage",
        "багаж",
        "bagaj",
        "gepäck",
    ],
    "breakfast": [
        "breakfast",
        "lunch",
        "dinner",
        "restaurant",
        "завтрак",
        "обед",
        "ужин",
        "ресторан",
        "kahvaltı",
        "öğle",
        "akşam yemeği",
        "frühstück",
        "mittag",
        "abendessen",
        "vegetarian",
        "вегетариан",
        "vejetaryen",
        "vegetarisch",
    ],
    "bars": ["bar", "бар", "drink", "напит", "içecek", "getränk"],
    "wi-fi": [
        "wi-fi",
        "wifi",
        "wi fi",
        "вайфай",
        "интернет",
        "internet",
        "wlan",
        "пароль",
        "şifre",
        "passwort",
        "password",
    ],
    "pools": [
        "pool",
        "бассейн",
        "havuz",
        "schwimmbad",
        "beach",
        "пляж",
        "plaj",
        "strand",
        "towel",
        "полотенц",
        "havlu",
        "handtuch",
        "sunbed",
        "шезлонг",
        "şezlong",
        "liege",
    ],
    "spa": [
        "spa",
        "спа",
        "massage",
        "массаж",
        "masaj",
        "sauna",
        "сауна",
        "hammam",
        "хаммам",
        "hamam",
        "fitness",
        "фитнес",
        "gym",
        "спортзал",
        "spor salonu",
    ],
    "kids": [
        "kids",
        "child",
        "дет",
        "ребён",
        "ребен",
        "çocuk",
        "kinder",
        "baby",
        "cot",
        "кроватк",
        "bebek",
    ],
    "transfers": [
        "transfer",
        "трансфер",
        "airport",
        "аэропорт",
        "havalimanı",
        "flughafen",
        "taxi",
        "такси",
        "taksi",
        "bus",
        "автобус",
        "otobüs",
    ],
    "parking": ["parking", "парков", "otopark", "parkplatz", "parken"],
    "laundry": ["laundry", "стирк", "прачечн", "çamaşır", "wäsche", "ironing", "глажк", "ütü"],
    "housekeeping": ["cleaning", "уборк", "temizlik", "reinigung", "housekeeping"],
    "pets": ["pet", "dog", "собак", "кошк", "животн", "köpek", "kedi", "hund", "katze", "haustier"],
    "smoking": ["smok", "курить", "курени", "курящ", "покур", "sigara", "rauch"],
    "emergencies": [
        "emergency",
        "doctor",
        "экстрен",
        "врач",
        "доктор",
        "скорая",
        "acil",
        "doktor",
        "notfall",
        "arzt",
    ],
    "payments": [
        "pay",
        "credit card",
        "cash",
        "оплат",
        "карт",
        "налич",
        "ödeme",
        "kredi kart",
        "nakit",
        "zahlung",
        "karte",
        "bar zahlen",
    ],
}

INTRO = {
    Language.EN: "From our hotel guide ({title}):",
    Language.RU: "Из справочника отеля ({title}, текст на английском):",
    Language.TR: "Otel rehberimizden ({title}, metin İngilizce):",
    Language.DE: "Aus unserem Hotelführer ({title}, Text auf Englisch):",
}


class MockLLM:
    async def answer(
        self, question: str, language: Language, knowledge: str, history: str
    ) -> ConciergeAnswer:
        sections = parse_sections(knowledge)
        text = question.lower()
        best, best_score = None, 0
        for section in sections:
            title = section.title.lower()
            score = sum(
                1
                for topic, words in TOPIC_KEYWORDS.items()
                if topic in title
                for word in words
                # Match at the start of a word: "pet" must not match "carpet".
                if re.search(rf"\b{re.escape(word)}", text)
            )
            if score > best_score:
                best, best_score = section, score

        if best is None:
            return ConciergeAnswer(
                found_in_knowledge_base=False, answer="", question_in_english=question
            )
        body = " ".join(line.lstrip("- ").strip() for line in best.body.splitlines() if line)
        intro = INTRO[language].format(title=best.title)
        return ConciergeAnswer(
            found_in_knowledge_base=True, answer=f"{intro} {body}", question_in_english=question
        )

    async def translate(self, text: str, target: Language) -> str:
        return text  # no translation offline
