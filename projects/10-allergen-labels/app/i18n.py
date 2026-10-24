"""The four menu languages and the fixed texts of the printed menu."""

from enum import StrEnum


class Language(StrEnum):
    EN = "en"
    RU = "ru"
    TR = "tr"
    DE = "de"

    @property
    def native_name(self) -> str:
        return _NATIVE[self]

    @property
    def english_name(self) -> str:
        return _ENGLISH[self]


_NATIVE = {
    Language.EN: "English",
    Language.RU: "Русский",
    Language.TR: "Türkçe",
    Language.DE: "Deutsch",
}
_ENGLISH = {
    Language.EN: "English",
    Language.RU: "Russian",
    Language.TR: "Turkish",
    Language.DE: "German",
}


def parse_language(value: str | None, default: Language = Language.EN) -> Language:
    """'de', 'DE' or 'de-AT' -> Language.DE; anything unknown -> default."""
    if not value:
        return default
    try:
        return Language(value.split("-")[0].strip().lower())
    except ValueError:
        return default


class Section(StrEnum):
    """Menu sections, in the order they are printed."""

    SOUPS = "soups"
    STARTERS = "starters"
    MAINS = "mains"
    DESSERTS = "desserts"
    DRINKS = "drinks"

    def label(self, language: Language) -> str:
        return _SECTIONS[self][language]


_SECTIONS: dict[Section, dict[Language, str]] = {
    Section.SOUPS: {
        Language.EN: "Soups",
        Language.RU: "Супы",
        Language.TR: "Çorbalar",
        Language.DE: "Suppen",
    },
    Section.STARTERS: {
        Language.EN: "Starters",
        Language.RU: "Закуски",
        Language.TR: "Başlangıçlar",
        Language.DE: "Vorspeisen",
    },
    Section.MAINS: {
        Language.EN: "Main courses",
        Language.RU: "Основные блюда",
        Language.TR: "Ana yemekler",
        Language.DE: "Hauptgerichte",
    },
    Section.DESSERTS: {
        Language.EN: "Desserts",
        Language.RU: "Десерты",
        Language.TR: "Tatlılar",
        Language.DE: "Desserts",
    },
    Section.DRINKS: {
        Language.EN: "Drinks",
        Language.RU: "Напитки",
        Language.TR: "İçecekler",
        Language.DE: "Getränke",
    },
}

# Fixed texts of the printed menu. The guest-facing note asks guests to talk to staff;
# it deliberately makes no promise about cross-contamination.
MENU_TEXT: dict[str, dict[Language, str]] = {
    "menu": {
        Language.EN: "Menu",
        Language.RU: "Меню",
        Language.TR: "Menü",
        Language.DE: "Speisekarte",
    },
    "allergens": {
        Language.EN: "Allergens",
        Language.RU: "Аллергены",
        Language.TR: "Alerjenler",
        Language.DE: "Allergene",
    },
    "legend_intro": {
        Language.EN: "The numbers next to each dish refer to this list of the 14 allergens that "
        "EU food law requires us to declare (Regulation (EU) No 1169/2011, Annex II).",
        Language.RU: "Цифры рядом с блюдом — номера из этого списка 14 аллергенов, которые "
        "по закону ЕС нужно указывать (Регламент (ЕС) № 1169/2011, Приложение II).",
        Language.TR: "Yemeklerin yanındaki numaralar, AB gıda mevzuatının bildirilmesini "
        "zorunlu tuttuğu 14 alerjenin bu listesindeki numaralardır (1169/2011 sayılı AB "
        "Tüzüğü, Ek II).",
        Language.DE: "Die Zahlen neben den Gerichten verweisen auf diese Liste der 14 Allergene, "
        "die nach EU-Recht angegeben werden müssen (Verordnung (EU) Nr. 1169/2011, Anhang II).",
    },
    "ask_staff": {
        Language.EN: "If you have a food allergy or intolerance, please tell our staff "
        "before you order.",
        Language.RU: "Если у вас пищевая аллергия или непереносимость, пожалуйста, "
        "скажите об этом официанту до заказа.",
        Language.TR: "Gıda alerjiniz veya intoleransınız varsa lütfen sipariş vermeden önce "
        "personelimize bildirin.",
        Language.DE: "Wenn Sie eine Lebensmittelallergie oder -unverträglichkeit haben, sagen "
        "Sie es bitte vor der Bestellung unserem Personal.",
    },
    "none": {
        Language.EN: "none of the 14",
        Language.RU: "нет из списка",
        Language.TR: "listedekilerden yok",
        Language.DE: "keines der 14",
    },
    "checked": {
        Language.EN: "Allergen information checked by our kitchen, last update {date}.",
        Language.RU: "Информация об аллергенах проверена нашей кухней, обновлено {date}.",
        Language.TR: "Alerjen bilgileri mutfağımız tarafından kontrol edildi, son güncelleme "
        "{date}.",
        Language.DE: "Allergeninformationen von unserer Küche geprüft, Stand {date}.",
    },
    "sample": {
        Language.EN: "Sample menu — demo data, not a real restaurant",
        Language.RU: "Пример меню — демо-данные, не настоящий ресторан",
        Language.TR: "Örnek menü — demo verisi, gerçek bir restoran değil",
        Language.DE: "Beispielkarte — Demodaten, kein echtes Restaurant",
    },
}


def menu_text(key: str, language: Language, **values: str) -> str:
    return MENU_TEXT[key][language].format(**values)
