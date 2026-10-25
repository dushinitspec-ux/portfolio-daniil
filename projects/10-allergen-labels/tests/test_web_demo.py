"""The adapter behind the in-browser demo (app/web_demo.py), run here on CPython."""

import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from app import web_demo
from app.demo import SAMPLE_DISHES
from app.text import recipe_hash

ROOT = Path(__file__).resolve().parent.parent
CHEF = "Aylin Demir"


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(web_demo, "_state", web_demo._State())


@pytest.fixture
async def setup() -> dict[str, Any]:
    return await web_demo.setup(120)


def item(result: dict[str, Any], label: str) -> dict[str, Any]:
    return next(i for i in result["items"] if i["label"] == label)


async def menu_dishes(language: str) -> dict[str, list[int]]:
    menu = await web_demo.menu(language)
    return {d["name"]: d["allergens"] for s in menu["sections"] for d in s["dishes"]}


async def test_setup_starts_with_confirmed_sample_dishes(setup: dict[str, Any]) -> None:
    assert [d["names"]["en"] for d in setup["dishes"]] == [
        "Red lentil soup (mercimek çorbası)",
        "Hummus",
        "Wiener schnitzel",
        "Pelmeni (meat dumplings) with sour cream",
        "Pistachio baklava",
        "Ayran (salted yogurt drink)",
    ]
    assert {d["state"] for d in setup["dishes"]} == {"confirmed"}
    assert all(d["sample"] for d in setup["dishes"])
    assert setup["ai"] is False
    assert len(setup["allergens"]) == 14
    assert setup["allergens"][4]["label"]["tr"] == "Yerfıstığı"
    carbonara, satay = setup["script"]
    by_name = {d.names[web_demo.Language.EN]: d for d in SAMPLE_DISHES}
    assert carbonara["recipe"] == by_name["Spaghetti carbonara"].recipe
    assert satay["changed_recipe"] == by_name["Chicken satay with peanut sauce"].changed_recipe
    json.dumps(setup)


def test_check_flags_an_unknown_ingredient() -> None:
    recipe = "spaghetti, egg yolk, pecorino, guanciale, black pepper"
    result = web_demo.check(recipe)
    assert result["allergens"] == [1, 3, 7]
    assert result["to_check"] == ["guanciale"]
    assert item(result, "guanciale")["unknown"] == ["guanciale"]
    assert item(result, "guanciale")["status"] == "check"
    assert item(result, "black pepper")["status"] == "none"
    assert result["hash"] == recipe_hash(recipe)


def test_check_explains_composite_products() -> None:
    result = web_demo.check(
        "chicken thigh, satay sauce (peanuts, soy sauce, coconut milk, lime), cucumber"
    )
    soy = item(result, "satay sauce › soy sauce")
    assert {(h["allergen"], h["certain"]) for h in soy["hits"]} == {(6, True), (1, False)}
    assert soy["status"] == "check"
    assert any("wheat" in note for note in soy["notes"])
    coconut = item(result, "satay sauce › coconut milk")
    assert coconut["hits"] == []
    assert any("Coconut" in note for note in coconut["notes"])
    assert result["certain"] == [5, 6]


def test_check_reads_all_four_languages() -> None:
    result = web_demo.check("süt, Weizenmehl, сливочное масло, egg")
    assert result["allergens"] == [1, 3, 7]
    assert result["to_check"] == []


async def test_saving_needs_a_name(setup: dict[str, Any]) -> None:
    result = await web_demo.save(None, {"en": "Soup"}, "soups", "water, salt", "  ")
    assert result == {
        "ok": False,
        "error": "Enter your name: every change is logged with who made it.",
    }
    assert len(await web_demo.dishes()) == len(setup["dishes"])


async def test_a_dish_reaches_the_menu_only_after_confirmation(setup: dict[str, Any]) -> None:
    carbonara = setup["script"][0]
    saved = await web_demo.save(
        None, carbonara["names"], carbonara["section"], carbonara["recipe"], CHEF
    )
    dish = saved["dish"]
    assert dish["state"] == "new"
    assert dish["preselected"] == [1, 3, 7]
    assert dish["analysis"]["to_check"] == ["guanciale"]
    assert "Spaghetti carbonara" not in await menu_dishes("en")
    assert (await web_demo.menu("en"))["hidden"] == ["Spaghetti carbonara"]

    confirmed = await web_demo.confirm(dish["id"], [1, 3, 7], CHEF, dish["recipe_hash"])
    assert confirmed["ok"] is True
    assert confirmed["dish"]["state"] == "confirmed"
    assert confirmed["dish"]["confirmation"]["by"] == CHEF
    assert [e["action"] for e in confirmed["dish"]["events"]] == ["confirmed", "created"]
    assert (await menu_dishes("en"))["Spaghetti carbonara"] == [1, 3, 7]
    assert (await menu_dishes("tr"))["Spagetti carbonara"] == [1, 3, 7]
    assert (await menu_dishes("de"))["Spaghetti Carbonara"] == [1, 3, 7]
    assert (await menu_dishes("ru"))["Спагетти карбонара"] == [1, 3, 7]


async def test_editing_the_recipe_resets_the_confirmation(setup: dict[str, Any]) -> None:
    satay = setup["script"][1]
    dish = (await web_demo.save(None, satay["names"], "mains", satay["recipe"], CHEF))["dish"]
    assert dish["preselected"] == [1, 5, 6]
    await web_demo.confirm(dish["id"], [1, 5, 6], CHEF, dish["recipe_hash"])

    edited = await web_demo.save(dish["id"], satay["names"], "mains", satay["changed_recipe"], CHEF)
    assert edited["reset"] is True
    assert edited["dish"]["state"] == "changed"
    assert edited["dish"]["confirmation"] is None
    assert edited["dish"]["last_confirmation"]["allergens"] == [1, 5, 6]
    assert edited["dish"]["preselected"] == [1, 2, 4, 5, 6]  # fish sauce: fish, maybe shrimp
    assert edited["dish"]["events"][0]["action"] == "confirmation reset"
    menu = await web_demo.menu("en")
    assert menu["hidden"] == ["Chicken satay with peanut sauce"]

    stale = await web_demo.confirm(dish["id"], [1, 5, 6], CHEF, dish["recipe_hash"])
    assert stale["ok"] is False
    assert stale["stale"] is True


async def test_a_missing_translation_falls_back_to_english(setup: dict[str, Any]) -> None:
    dish = (await web_demo.save(None, {"en": "Toast"}, "starters", "bread, butter", CHEF))["dish"]
    await web_demo.confirm(dish["id"], [1, 7], CHEF, dish["recipe_hash"])
    menu = await web_demo.menu("tr")
    [toast] = [d for s in menu["sections"] for d in s["dishes"] if d["id"] == dish["id"]]
    assert toast == {"id": dish["id"], "name": "Toast", "allergens": [1, 7], "translated": False}


async def test_menu_has_the_legend_and_fixed_texts(setup: dict[str, Any]) -> None:
    menu = await web_demo.menu("de")
    assert menu["title"] == "Sample Kitchen"
    assert [line["number"] for line in menu["legend"]] == list(range(1, 15))
    assert menu["legend"][7]["label"] == "Schalenfrüchte"
    assert menu["text"]["sample"].startswith("Beispielkarte")
    assert menu["text"]["checked"].startswith("Allergeninformationen von unserer Küche geprüft")
    assert [s["title"] for s in menu["sections"]] == [
        "Suppen",
        "Vorspeisen",
        "Hauptgerichte",
        "Desserts",
        "Getränke",
    ]


async def test_the_confirmation_log_stays_append_only(setup: dict[str, Any]) -> None:
    repo = web_demo._kitchen().repo
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        await repo.connection.execute("UPDATE confirmations SET confirmed_by = 'someone else'")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        await repo.connection.execute("DELETE FROM events")


async def test_setup_again_starts_a_new_kitchen(setup: dict[str, Any]) -> None:
    await web_demo.save(None, {"en": "Toast"}, "starters", "bread", CHEF)
    again = await web_demo.setup(0)
    assert len(again["dishes"]) == len(setup["dishes"])


def test_the_adapter_imports_nothing_the_browser_lacks() -> None:
    code = (
        "import sys, app.web_demo\n"
        "bad = {'fastapi', 'uvicorn', 'aiosqlite', 'anthropic', 'pydantic_settings', 'httpx',"
        " 'jinja2', 'tzdata'}\n"
        "print(sorted(m for m in sys.modules if m.split('.')[0] in bad))"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=True
    )
    assert out.stdout.strip() == "[]"


def test_web_demo_json_lists_every_module_the_adapter_needs() -> None:
    config = json.loads((ROOT / "web_demo.json").read_text("utf-8"))
    code = (
        "import sys, app.web_demo\n"
        "print('\\n'.join(sorted(m.__file__ for m in list(sys.modules.values())"
        " if getattr(m, '__file__', None) and m.__name__.startswith('app'))))"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=True
    )
    loaded = {Path(line).resolve().relative_to(ROOT).as_posix() for line in out.stdout.splitlines()}
    assert loaded <= set(config["files"])
    assert config["entry"] == "app.web_demo"
