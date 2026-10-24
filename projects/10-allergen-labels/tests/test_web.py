import re
from collections.abc import AsyncIterator
from zoneinfo import ZoneInfo

import httpx
import pytest

from app.demo import SAMPLE_DISHES, seed
from app.service import Kitchen
from app.web import create_app
from tests.conftest import T0


@pytest.fixture
async def client(kitchen: Kitchen) -> AsyncIterator[httpx.AsyncClient]:
    await seed(kitchen, T0)
    app = create_app(kitchen, title="Sample Kitchen", tz=ZoneInfo("Europe/Istanbul"), demo=True)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def dish_id(client: httpx.AsyncClient, english_name: str) -> int:
    dishes = (await client.get("/api/dishes")).json()
    return next(d["id"] for d in dishes if d["names"]["en"] == english_name)


async def test_dish_list(client: httpx.AsyncClient) -> None:
    html = (await client.get("/")).text
    assert "Menemen (eggs with tomatoes and peppers)" in html
    assert "Recipe changed" in html  # the satay
    assert "Not confirmed" in html  # carbonara, İskender
    assert "Demo · sample data" in html
    assert "does not replace your own allergen management" in html


async def test_dish_page_shows_matches_and_preselected_boxes(
    client: httpx.AsyncClient,
) -> None:
    carbonara = await dish_id(client, "Spaghetti carbonara")
    html = (await client.get(f"/dishes/{carbonara}")).text
    assert "Not in the dictionary: guanciale" in html
    assert "“pecorino” → pecorino" in html
    assert "AI suggestions are off" in html
    checked = re.findall(r'name="allergen" value="(\d+)" checked', html)
    assert checked == ["1", "3", "7"]


async def test_confirm_through_the_form(client: httpx.AsyncClient) -> None:
    carbonara = await dish_id(client, "Spaghetti carbonara")
    page = (await client.get(f"/dishes/{carbonara}")).text
    recipe_hash = re.search(r'name="recipe_hash" value="([0-9a-f]+)"', page).group(1)  # type: ignore[union-attr]

    missing_name = await client.post(
        f"/dishes/{carbonara}/confirm",
        data={"recipe_hash": recipe_hash, "actor": "", "allergen": ["1", "3", "7"]},
    )
    assert missing_name.status_code == 400

    resp = await client.post(
        f"/dishes/{carbonara}/confirm",
        data={"recipe_hash": recipe_hash, "actor": "Chef Anna", "allergen": ["1", "3", "7"]},
    )
    assert resp.status_code == 303
    assert resp.cookies.get("chef_name") is not None
    menu = (await client.get("/api/menu.json")).json()
    entry = next(d for d in menu["dishes"] if d["id"] == carbonara)
    assert entry["allergens"] == [1, 3, 7]
    assert entry["confirmed_by"] == "Chef Anna"


async def test_stale_confirmation_returns_409(client: httpx.AsyncClient) -> None:
    menemen = await dish_id(client, "Menemen (eggs with tomatoes and peppers)")
    resp = await client.post(
        f"/dishes/{menemen}/confirm",
        data={"recipe_hash": "0000000000000000", "actor": "Chef Anna", "allergen": ["3"]},
    )
    assert resp.status_code == 409
    assert "changed after you opened this page" in resp.text


async def test_editing_the_recipe_takes_the_dish_off_the_menu(client: httpx.AsyncClient) -> None:
    menemen = await dish_id(client, "Menemen (eggs with tomatoes and peppers)")
    resp = await client.post(
        f"/dishes/{menemen}",
        data={
            "name_en": "Menemen (eggs with tomatoes and peppers)",
            "name_tr": "Menemen",
            "section": "mains",
            "recipe": "yumurta, domates, sivri biber, soğan, tereyağı, beyaz peynir, sucuk",
            "actor": "Ali",
        },
    )
    assert resp.status_code == 303
    assert resp.headers["location"].endswith("saved=reset")
    page = (await client.get(resp.headers["location"])).text
    assert "confirmation was reset" in page
    menu = (await client.get("/menu?lang=tr")).text
    assert "Menemen" not in menu.split("<article")[1]


async def test_create_dish_and_validation(client: httpx.AsyncClient) -> None:
    bad = await client.post("/dishes", data={"name_en": "Toast", "recipe": "bread", "actor": ""})
    assert bad.status_code == 400
    assert "Enter your name" in bad.text
    ok = await client.post(
        "/dishes",
        data={"name_en": "Toast", "section": "starters", "recipe": "bread, butter", "actor": "Ali"},
    )
    assert ok.status_code == 303
    page = (await client.get(ok.headers["location"])).text
    assert "Toast" in page and "Not confirmed" in page


@pytest.mark.parametrize(
    ("lang", "expected"),
    [
        ("en", ["Allergens", "Main courses", "Nuts", "Cereals containing gluten", "Menemen"]),
        ("ru", ["Аллергены", "Основные блюда", "Орехи", "Злаки, содержащие глютен", "Борщ"]),
        ("tr", ["Alerjenler", "Ana yemekler", "Sert kabuklu meyveler", "Mercimek çorbası"]),
        (
            "de",
            [
                "Allergene",
                "Hauptgerichte",
                "Schalenfrüchte",
                "Glutenhaltiges Getreide",
                "Wiener Schnitzel",
            ],
        ),
    ],
)
async def test_printable_menu_per_language(
    client: httpx.AsyncClient, lang: str, expected: list[str]
) -> None:
    html = (await client.get(f"/menu?lang={lang}")).text
    assert f'<html lang="{lang}">' in html
    for text in expected:
        assert text in html, text
    assert "@media print" in html
    sheet = html.split("<article")[1]
    assert "carbonara" not in sheet.lower(), "unconfirmed dishes are not printed"
    assert re.search(r"<span>8</span>", sheet), "baklava shows nut number 8"


async def test_unconfirmed_dishes_are_listed_for_staff_only(client: httpx.AsyncClient) -> None:
    html = (await client.get("/menu?lang=en")).text
    note = html.split('<p class="hidden-note no-print">')[1].split("</p>")[0]
    assert "Spaghetti carbonara" in note and "İskender kebab" in note


async def test_json_export(client: httpx.AsyncClient) -> None:
    data = (await client.get("/api/menu.json?lang=de")).json()
    assert data["languages"] == ["de"]
    assert len(data["legend"]) == 14
    names = [d["name"]["de"] for d in data["dishes"]]
    confirmed = sum(d.confirmed is not None for d in SAMPLE_DISHES) - 1  # satay was reset
    assert len(names) == confirmed
    assert {d["name"] for d in data["not_published"]} == {
        "İskender kebab",
        "Spaghetti carbonara",
        "Chicken satay with peanut sauce",
    }


async def test_check_api(client: httpx.AsyncClient) -> None:
    data = (await client.post("/api/check", json={"ingredients": "tahin, fıstık"})).json()
    assert [a["number"] for a in data["allergens"]] == [5, 8, 11]
    assert data["needs_check"] == ["fıstık"]


async def test_healthz(client: httpx.AsyncClient) -> None:
    assert (await client.get("/healthz")).json() == {"status": "ok"}
