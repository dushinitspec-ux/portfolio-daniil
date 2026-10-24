import sqlite3

import pytest

from app.db import Repository
from app.i18n import Language, Section
from app.menu import build_menu, menu_json, published
from app.service import Kitchen, KitchenError, StaleRecipeError
from tests.conftest import NAMES, T0, Clock, FakeSuggester


async def add(kitchen: Kitchen, recipe: str = "yumurta, domates, tereyağı") -> int:
    return await kitchen.create(NAMES, Section.MAINS, recipe, "Ayşe")


async def confirm(kitchen: Kitchen, dish_id: int, numbers: set[int], actor: str = "Ayşe") -> int:
    view = await kitchen.get(dish_id)
    assert view is not None
    return await kitchen.confirm(dish_id, numbers, actor, view.row.recipe_hash)


async def test_new_dish_is_not_published(kitchen: Kitchen) -> None:
    dish_id = await add(kitchen)
    view = await kitchen.get(dish_id)
    assert view is not None
    assert not view.confirmed
    assert view.state == "new"
    assert view.suggested == {3, 7}
    assert published(await kitchen.dishes()) == []


async def test_confirmation_is_logged_with_who_and_when(kitchen: Kitchen) -> None:
    dish_id = await add(kitchen)
    await confirm(kitchen, dish_id, {3, 7}, actor="  Chef   Mehmet ")
    view = await kitchen.get(dish_id)
    assert view is not None and view.confirmation is not None
    assert view.state == "confirmed"
    assert view.confirmation.confirmed_by == "Chef Mehmet"
    assert view.confirmation.confirmed_at > T0
    assert view.confirmation.allergens == (3, 7)
    assert view.confirmation.recipe == "yumurta, domates, tereyağı"
    confirmations, events = await kitchen.history(dish_id)
    assert len(confirmations) == 1
    assert [e.action for e in events] == ["confirmed", "created"]
    assert published(await kitchen.dishes())[0].id == dish_id


async def test_confirmation_needs_a_name(kitchen: Kitchen) -> None:
    dish_id = await add(kitchen)
    with pytest.raises(KitchenError, match="name"):
        await confirm(kitchen, dish_id, {3, 7}, actor="   ")
    assert (await kitchen.history(dish_id))[0] == []


async def test_changing_the_recipe_resets_the_confirmation(kitchen: Kitchen) -> None:
    dish_id = await add(kitchen)
    await confirm(kitchen, dish_id, {3, 7})
    reset = await kitchen.update(
        dish_id, NAMES, Section.MAINS, "yumurta, domates, tereyağı, beyaz peynir", "Ali"
    )
    assert reset is True
    view = await kitchen.get(dish_id)
    assert view is not None
    assert not view.confirmed
    assert view.state == "changed"
    assert published(await kitchen.dishes()) == []
    confirmations, events = await kitchen.history(dish_id)
    assert len(confirmations) == 1, "the old confirmation stays in the log"
    assert events[0].action == "confirmation reset"
    assert events[0].actor == "Ali"


async def test_reverting_the_recipe_does_not_restore_the_old_confirmation(
    kitchen: Kitchen,
) -> None:
    dish_id = await add(kitchen)
    await confirm(kitchen, dish_id, {3, 7})
    await kitchen.update(dish_id, NAMES, Section.MAINS, "yumurta, domates", "Ali")
    await kitchen.update(dish_id, NAMES, Section.MAINS, "yumurta, domates, tereyağı", "Ali")
    view = await kitchen.get(dish_id)
    assert view is not None
    assert not view.confirmed


async def test_reordering_or_renaming_keeps_the_confirmation(kitchen: Kitchen) -> None:
    dish_id = await add(kitchen)
    await confirm(kitchen, dish_id, {3, 7})
    reset = await kitchen.update(
        dish_id, NAMES, Section.MAINS, "Tereyağı,\nDOMATES, yumurta", "Ali"
    )
    assert reset is False
    renamed = {**NAMES, Language.DE: "Menemen nach Hausart"}
    assert (
        await kitchen.update(
            dish_id, renamed, Section.STARTERS, "Tereyağı, DOMATES, yumurta", "Ali"
        )
        is False
    )
    view = await kitchen.get(dish_id)
    assert view is not None
    assert view.confirmed
    assert view.name(Language.DE) == "Menemen nach Hausart"


async def test_confirming_a_stale_page_is_refused(kitchen: Kitchen) -> None:
    dish_id = await add(kitchen)
    view = await kitchen.get(dish_id)
    assert view is not None
    opened_with = view.row.recipe_hash
    await kitchen.update(dish_id, NAMES, Section.MAINS, "yumurta, domates, tereyağı, un", "Ali")
    with pytest.raises(StaleRecipeError):
        await kitchen.confirm(dish_id, {3, 7}, "Ayşe", opened_with)
    assert (await kitchen.history(dish_id))[0] == []


async def test_unknown_allergen_number_is_refused(kitchen: Kitchen) -> None:
    dish_id = await add(kitchen)
    with pytest.raises(KitchenError):
        await confirm(kitchen, dish_id, {3, 15})


async def test_dish_needs_english_name_and_ingredients(kitchen: Kitchen) -> None:
    with pytest.raises(KitchenError, match="English name"):
        await kitchen.create({**NAMES, Language.EN: " "}, Section.MAINS, "süt", "Ayşe")
    with pytest.raises(KitchenError, match="ingredients"):
        await kitchen.create(NAMES, Section.MAINS, "  ", "Ayşe")


async def test_drift_when_the_dictionary_finds_more_than_was_confirmed(
    kitchen: Kitchen,
) -> None:
    dish_id = await add(kitchen)
    await confirm(kitchen, dish_id, {3})  # milk (tereyağı) left out
    view = await kitchen.get(dish_id)
    assert view is not None
    assert view.drift == {7}
    assert view.state == "review"
    assert view.confirmed, "it stays published until someone acts"


async def test_confirmation_log_is_append_only(kitchen: Kitchen, repo: Repository) -> None:
    dish_id = await add(kitchen)
    await confirm(kitchen, dish_id, {3, 7})
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        await repo.connection.execute("UPDATE confirmations SET confirmed_by = 'someone else'")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        await repo.connection.execute("DELETE FROM events")


async def test_archived_dish_leaves_the_menu(kitchen: Kitchen) -> None:
    dish_id = await add(kitchen)
    await confirm(kitchen, dish_id, {3, 7})
    await kitchen.set_archived(dish_id, True, "Ayşe")
    assert published(await kitchen.dishes(include_archived=True)) == []
    assert await kitchen.dishes() == []
    await kitchen.set_archived(dish_id, False, "Ayşe")
    assert len(published(await kitchen.dishes())) == 1


async def test_ai_suggestions_are_asked_once_and_cached(repo: Repository) -> None:
    suggester = FakeSuggester({"guanciale": [], "fıstık": ["nuts"]})
    kitchen = Kitchen(repo, suggester, Clock())
    dish_id = await kitchen.create(NAMES, Section.MAINS, "spaghetti, guanciale, fıstık", "Ali")
    assert suggester.calls == [("Test dish", ["guanciale", "fıstık"])]
    view = await kitchen.get(dish_id)
    assert view is not None
    assert view.suggestions["fıstık"].allergens == ("nuts",)
    assert view.suggestions["guanciale"].allergens == ()
    assert view.suggestions["fıstık"].model == "fake-model"
    assert 8 in view.suggested
    # Nothing new to ask: no second call.
    assert await kitchen.suggest(dish_id) == 0
    assert len(suggester.calls) == 1


async def test_ai_failure_leaves_items_for_the_chef(repo: Repository) -> None:
    kitchen = Kitchen(repo, FakeSuggester(fail=True), Clock())
    dish_id = await kitchen.create(NAMES, Section.MAINS, "guanciale", "Ali")
    view = await kitchen.get(dish_id)
    assert view is not None
    assert view.suggestions == {}
    assert [i.label for i in view.to_check] == ["guanciale"]


async def test_ai_suggestion_never_confirms_by_itself(repo: Repository) -> None:
    kitchen = Kitchen(repo, FakeSuggester({"guanciale": ["milk"]}), Clock())
    dish_id = await kitchen.create(NAMES, Section.MAINS, "guanciale", "Ali")
    view = await kitchen.get(dish_id)
    assert view is not None
    assert view.ai_allergens == {7}
    assert not view.confirmed


async def test_menu_shows_confirmed_allergens_per_language(kitchen: Kitchen) -> None:
    dish_id = await add(kitchen)
    await add(kitchen, "guanciale")  # not confirmed
    await confirm(kitchen, dish_id, {3, 7})
    dishes = await kitchen.dishes()
    from zoneinfo import ZoneInfo

    menu = build_menu(dishes, Language.DE, "Testküche", ZoneInfo("Europe/Istanbul"))
    assert [s.title for s in menu.sections] == ["Hauptgerichte"]
    assert menu.sections[0].dishes[0].name == "Testgericht"
    assert menu.sections[0].dishes[0].allergens == (3, 7)
    assert menu.legend[7].label == "Schalenfrüchte"
    assert menu.legend[7].detail.startswith("Mandeln, Haselnüsse")  # label not repeated
    assert menu.legend[0].detail.startswith("Glutenhaltiges Getreide")  # whole word kept
    assert menu.legend[2].detail == ""  # "Eier" says it all
    assert menu.hidden == ["Test dish"]
    data = menu_json(dishes, "Testküche", T0, Language.TR)
    assert [d["name"]["tr"] for d in data["dishes"]] == ["Deneme yemeği"]
    assert data["dishes"][0]["allergen_ids"] == ["eggs", "milk"]
    assert data["dishes"][0]["confirmed_by"] == "Ayşe"
    assert len(data["not_published"]) == 1
    assert len(data["legend"]) == 14
