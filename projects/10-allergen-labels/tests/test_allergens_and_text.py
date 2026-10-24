import pytest

from app.allergens import ALLERGEN_IDS, ALLERGENS, BY_NUMBER, numbers_label
from app.i18n import Language
from app.text import fold, fold_with_map, parse_ingredients, recipe_hash


def test_fourteen_groups_numbered_as_in_annex_ii() -> None:
    assert [a.number for a in ALLERGENS] == list(range(1, 15))
    assert len(set(ALLERGEN_IDS)) == 14
    assert [a.id for a in ALLERGENS] == [
        "gluten",
        "crustaceans",
        "eggs",
        "fish",
        "peanuts",
        "soybeans",
        "milk",
        "nuts",
        "celery",
        "mustard",
        "sesame",
        "sulphites",
        "lupin",
        "molluscs",
    ]


def test_every_group_has_a_name_in_four_languages() -> None:
    for allergen in ALLERGENS:
        for language in Language:
            assert allergen.name(language).strip()
            assert allergen.label(language).strip()


def test_official_wording() -> None:
    # Annex II after Delegated Regulation (EU) No 78/2014: spelt and khorasan are wheat.
    assert "wheat (such as spelt and khorasan wheat)" in BY_NUMBER[1].name(Language.EN)
    assert BY_NUMBER[8].name(Language.DE).startswith("Schalenfrüchte")
    assert BY_NUMBER[8].name(Language.TR).startswith("Sert kabuklu meyveler")
    assert BY_NUMBER[13].name(Language.TR) == "Acı bakla"
    assert "10 mg/kg" in BY_NUMBER[12].name(Language.EN)
    assert "lactitol" in BY_NUMBER[7].exceptions
    assert "fully refined soybean oil" in BY_NUMBER[6].exceptions


def test_numbers_label() -> None:
    assert numbers_label({7, 1, 3}) == "1, 3, 7"
    assert numbers_label(set()) == ""


@pytest.mark.parametrize(
    ("text", "folded"),
    [
        ("Süzme YOĞURT", "suzme yogurt"),
        ("İRMİK", "irmik"),  # "İ".lower() would leave a combining dot behind
        ("KIRMIZI", "kirmizi"),
        ("Straße", "strasse"),
        ("Crème fraîche", "creme fraiche"),
        ("Свёкла", "свекла"),
    ],
)
def test_fold(text: str, folded: str) -> None:
    assert fold(text) == folded


def test_fold_map_points_back_to_the_original_text() -> None:
    text = "Weißwein, İrmik"
    folded, index = fold_with_map(text)
    assert folded == "weisswein, irmik"
    start = folded.index("irmik")
    assert text[index[start] : index[start + 4] + 1] == "İrmik"


def test_parse_ingredients_with_brackets_and_separators() -> None:
    items = parse_ingredients(
        "Caesar dressing (egg yolk, anchovies (salted)); croutons\n• parmesan · salt"
    )
    assert [i.text for i in items] == ["Caesar dressing", "croutons", "parmesan", "salt"]
    dressing = items[0]
    assert [p.text for p in dressing.parts] == ["egg yolk", "anchovies"]
    assert [p.text for p in dressing.parts[1].parts] == ["salted"]


def test_parse_tolerates_broken_brackets() -> None:
    assert [i.text for i in parse_ingredients("butter), milk")] == ["butter", "milk"]
    items = parse_ingredients("pesto (basil, cashews")
    assert items[0].text == "pesto"
    assert [p.text for p in items[0].parts] == ["basil", "cashews"]


def test_recipe_hash_ignores_order_case_spacing_and_diacritics() -> None:
    base = recipe_hash("yumurta, süt, un")
    assert recipe_hash("UN,  sut\nYumurta") == base
    assert recipe_hash("yumurta, süt, un, tuz") != base
    assert recipe_hash("yumurta, süt, mısır unu") != base


def test_recipe_hash_sees_changes_inside_brackets() -> None:
    assert recipe_hash("pesto (basil, cashews)") != recipe_hash("pesto (basil, pine nuts)")
    assert recipe_hash("pesto (cashews, basil)") == recipe_hash("pesto (basil, cashews)")
