import json

import pytest

from app.cli import main
from app.demo import DEMO_CHEF, SAMPLE_DISHES, seed
from app.evaluate import evaluate, load
from app.i18n import Language
from app.matcher import analyse
from app.service import Kitchen
from tests.conftest import T0


async def test_demo_seed(kitchen: Kitchen) -> None:
    assert await seed(kitchen, T0) == len(SAMPLE_DISHES) == 16
    dishes = await kitchen.dishes()
    assert all(all(d.row.names[lang] for lang in Language) for d in dishes)
    names = {d.name(Language.TR) for d in dishes}
    assert {"Menemen", "Mercimek çorbası", "Fıstıklı baklava"} <= names
    states = [d.state for d in dishes]
    assert states.count("confirmed") == 13
    assert states.count("changed") == 1
    assert states.count("new") == 2
    assert all(d.row.updated_by == DEMO_CHEF for d in dishes)
    assert await seed(kitchen, T0) == 0, "an existing database is never re-seeded"


def test_sample_confirmations_cover_what_the_dictionary_is_sure_about() -> None:
    for dish in SAMPLE_DISHES:
        if dish.confirmed is not None:
            assert analyse(dish.recipe).certain <= dish.confirmed, dish.names[Language.EN]


def test_cli_check(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as done:
        main(["check", "spaghetti, egg yolk, pecorino, guanciale"])
    assert done.value.code == 0
    out = capsys.readouterr().out
    assert "Allergens: 1 Gluten · 3 Eggs · 7 Milk" in out
    assert "not in the dictionary: guanciale" in out
    assert "A person must check 1: guanciale" in out


def test_cli_check_german_labels_and_json(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["check", "--lang", "de", "Haselnüsse, Sojasoße"])
    assert "8 Schalenfrüchte" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        main(["check", "--json", "Haselnüsse, Sojasoße"])
    data = json.loads(capsys.readouterr().out)
    assert data["allergens"] == [1, 6, 8]
    assert data["certain"] == [6, 8]
    assert data["needs_check"] == ["Sojasoße"]


def test_labelled_sample_has_no_silent_misses() -> None:
    rows = load()
    report, _ = evaluate(rows)
    assert report.lines == len(rows) > 100
    assert {r.language for r in rows} == {"en", "ru", "tr", "de"}
    assert report.silent_misses == 0
    assert report.found == report.expected
    assert report.clean_lines == report.no_allergen_lines
