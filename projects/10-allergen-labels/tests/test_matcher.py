import pytest

from app.matcher import IngredientResult, Status, analyse, analyse_text

# Each of the 14 groups, with a word in each language. Many are inflected on purpose.
GROUP_WORDS = [
    (1, "en", "wholemeal bread"),
    (1, "ru", "пшеничная мука"),
    (1, "tr", "buğday unu"),
    (1, "de", "Dinkelmehl"),
    (2, "en", "tiger prawns"),
    (2, "ru", "креветки"),
    (2, "tr", "karides"),
    (2, "de", "Garnelen"),
    (3, "en", "eggs"),
    (3, "ru", "яйца"),
    (3, "tr", "yumurtalı"),
    (3, "de", "Eier"),
    (4, "en", "anchovies"),
    (4, "ru", "с лососем"),
    (4, "tr", "levrek"),
    (4, "de", "Räucherlachs"),
    (5, "en", "peanuts"),
    (5, "ru", "арахис"),
    (5, "tr", "yer fıstığı"),
    (5, "de", "Erdnüsse"),
    (6, "en", "tofu"),
    (6, "ru", "соевые бобы"),
    (6, "tr", "soya fasulyesi"),
    (6, "de", "Sojabohnen"),
    (7, "en", "butter"),
    (7, "ru", "сливочное масло"),
    (7, "tr", "kaşar peyniri"),
    (7, "de", "Schlagsahne"),
    (8, "en", "almonds"),
    (8, "ru", "фундук"),
    (8, "tr", "fındığı"),
    (8, "de", "Haselnüsse"),
    (9, "en", "celeriac"),
    (9, "ru", "сельдерей"),
    (9, "tr", "kereviz"),
    (9, "de", "Knollensellerie"),
    (10, "en", "wholegrain mustard"),
    (10, "ru", "с горчицей"),
    (10, "tr", "hardallı"),
    (10, "de", "Senf"),
    (11, "en", "sesame seeds"),
    (11, "ru", "кунжутом"),
    (11, "tr", "tahinli"),
    (11, "de", "Sesam"),
    (12, "en", "sulphites"),
    (12, "ru", "сульфиты"),
    (12, "tr", "sülfit"),
    (12, "de", "geschwefelt"),
    (13, "en", "lupin flour"),
    (13, "ru", "люпин"),
    (13, "tr", "acı bakla"),
    (13, "de", "Lupinenmehl"),
    (14, "en", "mussels"),
    (14, "ru", "мидии"),
    (14, "tr", "kalamar"),
    (14, "de", "Miesmuscheln"),
]


@pytest.mark.parametrize(("group", "language", "text"), GROUP_WORDS)
def test_each_group_in_each_language(group: int, language: str, text: str) -> None:
    result = analyse_text(text)
    assert group in result.certain, (text, result.hits, result.unknown)


def test_group_table_covers_all_14_groups_in_4_languages() -> None:
    pairs = {(group, language) for group, language, _ in GROUP_WORDS}
    assert len(pairs) == 14 * 4


def one(text: str) -> IngredientResult:
    items = analyse(text).items
    assert len(items) == 1
    return items[0]


# --- morphology -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "group"),
    [
        ("молоком", 7),
        ("сметаной", 7),
        ("десяток яиц", 3),
        ("с грецкими орехами", 8),
        ("500 г креветок", 2),
        ("ржаной хлеб", 1),
    ],
)
def test_russian_case_endings(text: str, group: int) -> None:
    assert group in one(text).certain


@pytest.mark.parametrize(
    ("text", "group"),
    [
        ("fındığı", 8),  # k -> ğ before a vowel
        ("sütü", 7),
        ("peynirli", 7),
        ("ekmeği", 1),
        ("tereyağlı", 7),
        ("SÜT", 7),
        ("PEYNİR", 7),
        ("İRMİK", 1),
    ],
)
def test_turkish_suffixes_and_capitals(text: str, group: int) -> None:
    assert group in one(text).certain


@pytest.mark.parametrize(
    ("text", "group"),
    [
        ("Vollmilchschokolade", 7),
        ("Haselnusskrokant", 8),
        ("Hühnereier", 3),
        ("Hartweizengrieß", 1),
        ("Dijonsenf", 10),
    ],
)
def test_german_compounds(text: str, group: int) -> None:
    assert group in one(text).certain


def test_german_adjective_endings_are_known_words() -> None:
    # Regression: "gehackt" + "e" was reported as an unknown word (BUGFIX.md, bug 1).
    for text in ("gehackte Walnüsse", "geriebener Parmesan", "frische Kräuter"):
        assert one(text).unknown == [], text


@pytest.mark.parametrize("text", ["sut", "findik", "Haselnusse", "yogurt", "Kase"])
def test_typed_without_diacritics(text: str) -> None:
    assert one(text).allergens


def test_english_plurals() -> None:
    assert 4 in one("anchovies").certain
    assert one("tomatoes").status is Status.NONE


@pytest.mark.parametrize(
    "text",
    [
        "сырой картофель",  # raw, not cheese (сыр)
        "печень",  # liver, not biscuits (печенье)
        "Reis",  # rice: "Ei" is egg only as a whole word
        "Schweinefleisch",  # pork: "Wein" inside the word is not wine
        "Weintrauben",  # grapes
        "biraz tuz",  # "a little salt": not beer (bira)
        "bezelye",  # peas: not meringue (beze)
        "arpacık soğan",  # shallots: not barley (arpa)
        "маслины",  # olives, not "масло"
    ],
)
def test_false_friends_are_not_allergens(text: str) -> None:
    result = one(text)
    assert result.allergens == set(), result.hits


def test_cyrillic_celery_is_not_fish() -> None:
    result = one("сельдерей")
    assert result.certain == {9}


def test_matched_word_is_shown_as_written() -> None:
    hit = one("Fındığı").hits[0]
    assert hit.found == "Fındığı"
    assert hit.term == "fındık"
    assert hit.language.value == "tr"


# --- Annex II exclusions and look-alikes -------------------------------------------------


@pytest.mark.parametrize(
    ("text", "not_group"),
    [
        ("coconut milk", 7),
        ("coconut", 8),
        ("hindistan cevizi", 8),
        ("Kokosnuss", 8),
        ("кокосовое молоко", 7),
        ("pine nuts", 8),
        ("çam fıstığı", 8),
        ("Pinienkerne", 8),
        ("кедровые орехи", 8),
        ("nutmeg", 8),
        ("Muskatnuss", 8),
        ("buckwheat", 1),
        ("karabuğday", 1),
        ("Buchweizen", 1),
        ("гречка", 1),
        ("glucose syrup", 1),
        ("maltodextrin", 1),
        ("dextrose", 1),
        ("soybean oil", 6),
        ("cocoa butter", 7),
        ("eggplant", 3),
        ("cream of tartar", 7),
        ("whisky", 1),
    ],
)
def test_annex_ii_exclusions(text: str, not_group: int) -> None:
    result = one(text)
    assert not_group not in result.allergens
    assert result.notes, "an exclusion always explains itself"


def test_peanut_butter_is_peanuts_not_milk() -> None:
    assert one("peanut butter").allergens == {5}


def test_exclusion_note_quotes_annex_ii() -> None:
    assert "fully refined" in one("soybean oil").notes[0]
    assert "glucose syrups" in one("glucose syrup").notes[0]


# --- free-from claims never remove an allergen ----------------------------------------


def test_lactose_free_milk_is_still_milk() -> None:
    result = one("lactose-free milk")
    assert 7 in result.certain
    assert result.status is Status.CHECK


def test_gluten_free_pasta_still_needs_a_check() -> None:
    result = one("gluten-free pasta")
    assert 1 in result.allergens
    assert result.free_from


@pytest.mark.parametrize("text", ["yumurtasız", "sütsüz", "без глютена", "glutenfrei"])
def test_without_words_are_flagged_not_counted(text: str) -> None:
    result = one(text)
    assert result.allergens == set()
    assert result.status is Status.CHECK
    assert result.free_from


# --- composite products -------------------------------------------------------------


def test_pesto_is_possible_milk_and_nuts() -> None:
    result = one("pesto")
    assert result.allergens == {7, 8}
    assert result.certain == set()
    assert result.status is Status.CHECK


def test_listed_parts_replace_the_product_guess() -> None:
    items = analyse("pesto (basil, pine nuts, olive oil, garlic)").items
    assert items[0].text == "pesto" and items[0].allergens == set()
    assert [i.parent for i in items[1:]] == ["pesto"] * 4
    assert analyse("pesto (basil, pine nuts, olive oil, garlic)").allergens == set()


def test_caesar_dressing_from_its_parts() -> None:
    analysis = analyse("Caesar dressing (egg yolk, anchovies)")
    assert analysis.allergens == {3, 4}
    assert analysis.items[2].label == "Caesar dressing › anchovies"


@pytest.mark.parametrize(
    ("text", "certain", "possible"),
    [
        ("soy sauce", {6}, {1}),
        ("Sojasoße", {6}, {1}),
        ("соевый соус", {6}, {1}),
        ("Worcestershire sauce", set(), {1, 4}),
        ("tahini", {11}, set()),
        ("mayonnaise", {3}, {10}),
        ("hummus", {11}, set()),
        ("simit", {1, 11}, set()),
        ("oat milk", {1}, set()),
    ],
)
def test_composite_products(text: str, certain: set[int], possible: set[int]) -> None:
    result = one(text)
    assert result.certain == certain
    assert result.uncertain == possible


# --- ambiguous and unknown words ------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "candidates"),
    [
        ("fıstık", {5, 8}),
        ("масло", {7}),
        ("shellfish", {2, 4, 14}),
        ("barbunya", {4}),
        ("yağ", {7}),
    ],
)
def test_ambiguous_words_offer_candidates(text: str, candidates: set[int]) -> None:
    result = one(text)
    assert result.uncertain == candidates
    assert result.status is Status.CHECK


def test_specific_forms_resolve_the_ambiguity() -> None:
    assert one("antep fıstığı").certain == {8}
    assert one("yer fıstığı").certain == {5}
    assert one("оливковое масло").allergens == set()
    assert one("barbunya pilaki").allergens == set()


def test_unknown_words_are_reported() -> None:
    result = one("guanciale")
    assert result.status is Status.CHECK
    assert result.unknown == ["guanciale"]


def test_a_known_safe_part_does_not_hide_an_unknown_compound() -> None:
    # "Salat" is known, but a Waldorf salad has celery, walnuts and mayonnaise.
    assert one("Waldorfsalat").unknown == ["Waldorfsalat"]


@pytest.mark.parametrize("text", ["XO", "f?st?k", "f�st�k"])
def test_a_line_with_nothing_recognised_is_never_none(text: str) -> None:
    # Regression (BUGFIX.md, bug 4): short words are skipped as filler, which used to
    # make "XO" (a sauce with dried shrimp) and garbled text pass as "no allergen".
    result = one(text)
    assert result.status is Status.CHECK
    assert result.unknown == [text]


def test_garbled_word_next_to_a_known_one_is_flagged() -> None:
    result = one("süt f?st?k")
    assert result.certain == {7}
    assert result.unknown == ["f?st?k"]
    assert any("encoding" in note for note in result.notes)


def test_quantities_and_units_are_ignored() -> None:
    result = one("200 g unsalted butter")
    assert result.status is Status.FOUND
    assert result.certain == {7}


def test_spaghetti_carbonara_example() -> None:
    analysis = analyse("spaghetti, egg yolk, pecorino, guanciale")
    assert analysis.certain == {1, 3, 7}
    assert [i.label for i in analysis.to_check] == ["guanciale"]
