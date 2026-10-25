"""The 14 allergen groups of Regulation (EU) No 1169/2011, Annex II.

Numbers and wording follow the consolidated text of 1 January 2018 (EUR-Lex CELEX
02011R1169-20180101), which includes the change to point 1 made by Delegated Regulation
(EU) No 78/2014 ("wheat (such as spelt and khorasan wheat)").

- English and German names are the official wording of Annex II in those languages.
- Turkish names are the wording of Ek-1 of the Turkish Food Codex labelling regulation
  (Türk Gıda Kodeksi Gıda Etiketleme ve Tüketicileri Bilgilendirme Yönetmeliği,
  Resmî Gazete 26.01.2017, No 29960), which lists the same 14 groups in the same order.
- Russian is not an EU language, so the Russian names are my translation.

`exceptions` summarises what Annex II itself excludes from a group. It is shown to the chef
as a hint, not applied automatically, except where the dictionary has a matching entry.
"""

from dataclasses import dataclass

from app.i18n import Language

EN, RU, TR, DE = Language.EN, Language.RU, Language.TR, Language.DE


@dataclass(frozen=True)
class Allergen:
    number: int
    id: str
    names: dict[Language, str]  # wording of the regulation (Russian: translation)
    short: dict[Language, str]  # short label for menus and the UI
    exceptions: str = ""

    def name(self, language: Language) -> str:
        return self.names[language]

    def label(self, language: Language) -> str:
        return self.short[language]


ALLERGENS: tuple[Allergen, ...] = (
    Allergen(
        1,
        "gluten",
        {
            EN: "Cereals containing gluten: wheat (such as spelt and khorasan wheat), rye, "
            "barley, oats",
            RU: "Злаки, содержащие глютен: пшеница (в том числе спельта и хорасанская "
            "пшеница), рожь, ячмень, овёс",
            TR: "Gluten içeren tahıllar: buğday (ör. kılçıksız buğday ve kamut), çavdar, "
            "arpa, yulaf",
            DE: "Glutenhaltiges Getreide: Weizen (wie Dinkel und Khorasan-Weizen), Roggen, "
            "Gerste, Hafer",
        },
        {EN: "Gluten", RU: "Глютен", TR: "Gluten", DE: "Gluten"},
        "Not included: wheat-based glucose syrups including dextrose, wheat-based "
        "maltodextrins, glucose syrups based on barley, cereals used for making alcoholic "
        "distillates.",
    ),
    Allergen(
        2,
        "crustaceans",
        {EN: "Crustaceans", RU: "Ракообразные", TR: "Kabuklular", DE: "Krebstiere"},
        {EN: "Crustaceans", RU: "Ракообразные", TR: "Kabuklular", DE: "Krebstiere"},
    ),
    Allergen(
        3,
        "eggs",
        {EN: "Eggs", RU: "Яйца", TR: "Yumurta", DE: "Eier"},
        {EN: "Eggs", RU: "Яйца", TR: "Yumurta", DE: "Eier"},
    ),
    Allergen(
        4,
        "fish",
        {EN: "Fish", RU: "Рыба", TR: "Balık", DE: "Fische"},
        {EN: "Fish", RU: "Рыба", TR: "Balık", DE: "Fisch"},
        "Not included: fish gelatine used as a carrier for vitamin or carotenoid "
        "preparations; fish gelatine or isinglass used as a fining agent in beer and wine.",
    ),
    Allergen(
        5,
        "peanuts",
        {EN: "Peanuts", RU: "Арахис", TR: "Yerfıstığı", DE: "Erdnüsse"},
        {EN: "Peanuts", RU: "Арахис", TR: "Yerfıstığı", DE: "Erdnüsse"},
    ),
    Allergen(
        6,
        "soybeans",
        {EN: "Soybeans", RU: "Соя (соевые бобы)", TR: "Soya fasulyesi", DE: "Sojabohnen"},
        {EN: "Soy", RU: "Соя", TR: "Soya", DE: "Soja"},
        "Not included: fully refined soybean oil and fat; natural mixed tocopherols (E306) "
        "and natural D-alpha tocopherol and its acetate and succinate from soybean sources; "
        "phytosterols and phytosterol esters and plant stanol ester from soybean sources.",
    ),
    Allergen(
        7,
        "milk",
        {
            EN: "Milk (including lactose)",
            RU: "Молоко (включая лактозу)",
            TR: "Süt (laktoz dahil)",
            DE: "Milch (einschließlich Laktose)",
        },
        {EN: "Milk", RU: "Молоко", TR: "Süt", DE: "Milch"},
        "Not included: whey used for making alcoholic distillates; lactitol.",
    ),
    Allergen(
        8,
        "nuts",
        {
            EN: "Nuts: almonds, hazelnuts, walnuts, cashews, pecan nuts, Brazil nuts, "
            "pistachio nuts, macadamia or Queensland nuts",
            RU: "Орехи: миндаль, лесной орех (фундук), грецкий орех, кешью, пекан, "
            "бразильский орех, фисташки, макадамия",
            TR: "Sert kabuklu meyveler: badem, fındık, ceviz, kaju fıstığı, pikan cevizi, "
            "brezilya fındığı, antep fıstığı, macadamia fındığı",
            DE: "Schalenfrüchte: Mandeln, Haselnüsse, Walnüsse, Kaschunüsse, Pecannüsse, "
            "Paranüsse, Pistazien, Macadamia- oder Queenslandnüsse",
        },
        {EN: "Nuts", RU: "Орехи", TR: "Sert kabuklu meyveler", DE: "Schalenfrüchte"},
        "Only the eight nuts named in Annex II. Peanuts are group 5. Coconut, pine nuts, "
        "chestnuts and nutmeg are not on the list. Not included: nuts used for making "
        "alcoholic distillates.",
    ),
    Allergen(
        9,
        "celery",
        {EN: "Celery", RU: "Сельдерей", TR: "Kereviz", DE: "Sellerie"},
        {EN: "Celery", RU: "Сельдерей", TR: "Kereviz", DE: "Sellerie"},
    ),
    Allergen(
        10,
        "mustard",
        {EN: "Mustard", RU: "Горчица", TR: "Hardal", DE: "Senf"},
        {EN: "Mustard", RU: "Горчица", TR: "Hardal", DE: "Senf"},
    ),
    Allergen(
        11,
        "sesame",
        {EN: "Sesame seeds", RU: "Кунжут", TR: "Susam tohumu", DE: "Sesamsamen"},
        {EN: "Sesame", RU: "Кунжут", TR: "Susam", DE: "Sesam"},
    ),
    Allergen(
        12,
        "sulphites",
        {
            EN: "Sulphur dioxide and sulphites (more than 10 mg/kg or 10 mg/litre as SO2)",
            RU: "Диоксид серы и сульфиты (более 10 мг/кг или 10 мг/л в пересчёте на SO2)",
            TR: "Kükürt dioksit ve sülfitler (toplam SO2 olarak 10 mg/kg veya 10 mg/L'den fazla)",
            DE: "Schwefeldioxid und Sulphite (mehr als 10 mg/kg oder 10 mg/l als SO2)",
        },
        {EN: "Sulphites", RU: "Сульфиты", TR: "Sülfitler", DE: "Sulfite"},
        "Only above 10 mg/kg or 10 mg/litre in terms of total SO2, calculated for the "
        "product as ready for consumption. The dictionary cannot know the concentration, "
        "so it marks typical sources (wine, dried apricots) as 'check'.",
    ),
    Allergen(
        13,
        "lupin",
        {EN: "Lupin", RU: "Люпин", TR: "Acı bakla", DE: "Lupinen"},
        {EN: "Lupin", RU: "Люпин", TR: "Acı bakla", DE: "Lupinen"},
    ),
    Allergen(
        14,
        "molluscs",
        {EN: "Molluscs", RU: "Моллюски", TR: "Yumuşakçalar", DE: "Weichtiere"},
        {EN: "Molluscs", RU: "Моллюски", TR: "Yumuşakçalar", DE: "Weichtiere"},
    ),
)

BY_NUMBER: dict[int, Allergen] = {a.number: a for a in ALLERGENS}
BY_ID: dict[str, Allergen] = {a.id: a for a in ALLERGENS}
ALLERGEN_IDS: tuple[str, ...] = tuple(a.id for a in ALLERGENS)


def get(number: int) -> Allergen:
    return BY_NUMBER[number]


def numbers_label(numbers: set[int] | list[int] | tuple[int, ...]) -> str:
    """{7, 1, 3} -> '1, 3, 7'."""
    return ", ".join(str(n) for n in sorted(numbers))
