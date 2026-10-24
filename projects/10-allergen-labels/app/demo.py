"""Demo mode: a SAMPLE menu of 16 dishes for a made-up restaurant ("Sample Kitchen").

Recipes are written the way a kitchen in Antalya might keep them: Turkish dishes in
Turkish, a schnitzel in German, Russian dishes in Russian, the rest in English. Names are
given in all four languages.

The seed goes through the normal Kitchen API, so the demo shows every state a dish can be
in: confirmed by the (sample) chef, never confirmed because of an unknown ingredient, and
"recipe changed, confirmation reset".
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.i18n import Language, Section
from app.service import Kitchen

DEMO_CHEF = "Demo chef (sample data)"
EN, RU, TR, DE = Language.EN, Language.RU, Language.TR, Language.DE


@dataclass(frozen=True)
class SampleDish:
    section: Section
    names: dict[Language, str]
    recipe: str
    # None: the sample chef has not confirmed it yet. Otherwise the confirmed numbers.
    confirmed: frozenset[int] | None = None
    # A later recipe change (the confirmation is reset by it).
    changed_recipe: str | None = None


SAMPLE_DISHES: tuple[SampleDish, ...] = (
    SampleDish(
        Section.SOUPS,
        {
            EN: "Red lentil soup (mercimek çorbası)",
            RU: "Суп из красной чечевицы (мерджимек)",
            TR: "Mercimek çorbası",
            DE: "Rote Linsensuppe (Mercimek)",
        },
        "kırmızı mercimek, soğan, havuç, tereyağı, un, kimyon, pul biber, tuz, limon",
        confirmed=frozenset({1, 7}),
    ),
    SampleDish(
        Section.SOUPS,
        {
            EN: "Borscht with sour cream",
            RU: "Борщ со сметаной",
            TR: "Smetanalı borş çorbası",
            DE: "Borschtsch mit Schmand",
        },
        "свёкла, капуста, картофель, морковь, лук, томатная паста, говядина, сметана, "
        "укроп, чеснок, соль",
        confirmed=frozenset({7}),
    ),
    SampleDish(
        Section.STARTERS,
        {EN: "Hummus", RU: "Хумус", TR: "Humus", DE: "Hummus"},
        "chickpeas, tahini, lemon juice, garlic, olive oil, cumin, salt",
        confirmed=frozenset({11}),
    ),
    SampleDish(
        Section.STARTERS,
        {
            EN: "Cacık (yogurt with cucumber and mint)",
            RU: "Джаджик (йогурт с огурцом и мятой)",
            TR: "Cacık",
            DE: "Cacık (Joghurt mit Gurke und Minze)",
        },
        "süzme yoğurt, salatalık, sarımsak, nane, dereotu, zeytinyağı, tuz",
        confirmed=frozenset({7}),
    ),
    SampleDish(
        Section.STARTERS,
        {
            EN: "Caesar salad",
            RU: "Салат «Цезарь»",
            TR: "Sezar salata",
            DE: "Caesar Salad",
        },
        "romaine lettuce, croutons, parmesan, Caesar dressing (egg yolk, anchovies, "
        "Dijon mustard, Worcestershire sauce, lemon juice, olive oil)",
        confirmed=frozenset({1, 3, 4, 7, 10}),
    ),
    SampleDish(
        Section.STARTERS,
        {
            EN: "Stuffed mussels (midye dolma)",
            RU: "Фаршированные мидии (мидье долма)",
            TR: "Midye dolma",
            DE: "Gefüllte Miesmuscheln (Midye Dolma)",
        },
        "midye, pirinç, soğan, çam fıstığı, kuş üzümü, tarçın, yenibahar, zeytinyağı, limon",
        confirmed=frozenset({14}),
    ),
    SampleDish(
        Section.MAINS,
        {
            EN: "Menemen (eggs with tomatoes and peppers)",
            RU: "Менемен (яйца с помидорами и перцем)",
            TR: "Menemen",
            DE: "Menemen (Eier mit Tomaten und Paprika)",
        },
        "yumurta, domates, sivri biber, soğan, tereyağı, beyaz peynir, tuz, karabiber",
        confirmed=frozenset({3, 7}),
    ),
    SampleDish(
        Section.MAINS,
        {
            EN: "İskender kebab",
            RU: "Искендер-кебаб",
            TR: "İskender kebap",
            DE: "İskender Kebap",
        },
        "dana döner, pide, domates sosu, tereyağı, süzme yoğurt",
    ),
    SampleDish(
        Section.MAINS,
        {
            EN: "Spaghetti carbonara",
            RU: "Спагетти карбонара",
            TR: "Spagetti carbonara",
            DE: "Spaghetti Carbonara",
        },
        "spaghetti, egg yolk, pecorino, guanciale, black pepper",
    ),
    SampleDish(
        Section.MAINS,
        {
            EN: "Garlic prawns",
            RU: "Креветки с чесноком",
            TR: "Sarımsaklı karides",
            DE: "Knoblauchgarnelen",
        },
        "prawns, garlic, butter, white wine, parsley, chilli flakes",
        confirmed=frozenset({2, 7, 12}),
    ),
    SampleDish(
        Section.MAINS,
        {
            EN: "Wiener schnitzel",
            RU: "Венский шницель",
            TR: "Viyana şnitzeli",
            DE: "Wiener Schnitzel",
        },
        "Kalbfleisch, Weizenmehl, Eier, Semmelbrösel, Butterschmalz, Zitrone, Petersilie",
        confirmed=frozenset({1, 3, 7}),
    ),
    SampleDish(
        Section.MAINS,
        {
            EN: "Pelmeni (meat dumplings) with sour cream",
            RU: "Пельмени со сметаной",
            TR: "Smetanalı pelmeni (etli hamur bohçası)",
            DE: "Pelmeni (Teigtaschen mit Fleisch) mit Schmand",
        },
        "пшеничная мука, яйцо, вода, соль, свинина, говядина, лук, чёрный перец, сметана",
        confirmed=frozenset({1, 3, 7}),
    ),
    SampleDish(
        Section.MAINS,
        {
            EN: "Chicken satay with peanut sauce",
            RU: "Куриный сатай с арахисовым соусом",
            TR: "Yer fıstığı soslu tavuk satay",
            DE: "Hähnchen-Satay mit Erdnusssoße",
        },
        "chicken thigh, satay sauce (peanuts, soy sauce, coconut milk, lime, brown sugar, "
        "chilli), cucumber",
        confirmed=frozenset({1, 5, 6}),
        changed_recipe="chicken thigh, satay sauce (peanuts, soy sauce, fish sauce, coconut "
        "milk, lime, brown sugar, chilli), cucumber",
    ),
    SampleDish(
        Section.DESSERTS,
        {
            EN: "Pistachio baklava",
            RU: "Пахлава с фисташками",
            TR: "Fıstıklı baklava",
            DE: "Pistazien-Baklava",
        },
        "yufka, antep fıstığı, tereyağı, şeker, su, limon suyu",
        confirmed=frozenset({1, 7, 8}),
    ),
    SampleDish(
        Section.DESSERTS,
        {
            EN: "Rice pudding (sütlaç)",
            RU: "Рисовый пудинг (сютлач)",
            TR: "Fırın sütlaç",
            DE: "Milchreis (Sütlaç)",
        },
        "süt, pirinç, şeker, pirinç unu, vanilya, tarçın",
        confirmed=frozenset({7}),
    ),
    SampleDish(
        Section.DRINKS,
        {EN: "Ayran (salted yogurt drink)", RU: "Айран", TR: "Ayran", DE: "Ayran (Joghurtgetränk)"},
        "yoğurt, su, tuz",
        confirmed=frozenset({7}),
    ),
)


async def seed(kitchen: Kitchen, now: datetime) -> int:
    """Fill an empty database with the sample menu. Returns the number of dishes."""
    if await kitchen.repo.count_dishes():
        return 0
    real_clock = kitchen.clock
    start = now - timedelta(days=2)
    step = 0

    def tick() -> datetime:
        nonlocal step
        step += 1
        return start + timedelta(minutes=7 * step)

    kitchen.clock = tick
    try:
        changed: list[tuple[int, SampleDish]] = []
        for dish in SAMPLE_DISHES:
            dish_id = await kitchen.create(dish.names, dish.section, dish.recipe, DEMO_CHEF)
            if dish.confirmed is not None:
                view = await kitchen.get(dish_id)
                assert view is not None
                await kitchen.confirm(
                    dish_id, set(dish.confirmed), DEMO_CHEF, view.row.recipe_hash, "sample data"
                )
            if dish.changed_recipe:
                changed.append((dish_id, dish))
        # The recipe change happens "this morning", after everything was confirmed.
        start = now - timedelta(hours=3)
        step = 0
        for dish_id, dish in changed:
            assert dish.changed_recipe is not None
            await kitchen.update(dish_id, dish.names, dish.section, dish.changed_recipe, DEMO_CHEF)
    finally:
        kitchen.clock = real_clock
    return len(SAMPLE_DISHES)
