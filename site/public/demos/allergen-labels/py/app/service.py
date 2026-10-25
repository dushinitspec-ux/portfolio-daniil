"""The kitchen's dish list and the rules that keep allergen information honest.

- A dish is on the published menu only while it has a confirmation for its *current*
  recipe. Confirming needs a person's name; every confirmation is stored in an
  append-only log with who and when.
- Changing the ingredients resets the confirmation. Changing back to an old recipe does
  not bring the old confirmation back: someone confirms again.
- A confirmation is refused if the recipe changed after the confirming person opened the
  page (the form carries the recipe hash it was made for).
- The dictionary analysis is recomputed on every read, so improvements to the dictionary
  show up at once; if it now finds an allergen that a confirmation left out, the dish is
  flagged for review (it stays published until someone re-confirms or edits it).
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app import allergens as annex
from app.db import CachedSuggestion, Confirmation, DishRow, Event, Repository
from app.i18n import Language, Section
from app.llm import LLMError, Suggester
from app.matcher import Analysis, IngredientResult, analyse
from app.text import fold, recipe_hash

logger = logging.getLogger(__name__)


class KitchenError(Exception):
    """A request the rules do not allow; the message is shown to the user."""


class StaleRecipeError(KitchenError):
    pass


def utcnow() -> datetime:
    return datetime.now(UTC)


def suggestion_key(ingredient: str, dish_name: str) -> str:
    return f"{' '.join(fold(ingredient).split())}|{' '.join(fold(dish_name).split())}"


@dataclass
class DishView:
    row: DishRow
    analysis: Analysis
    suggestions: dict[str, CachedSuggestion] = field(default_factory=dict)  # by item label
    confirmation: Confirmation | None = None  # valid for the current recipe
    last_confirmation: Confirmation | None = None  # most recent, valid or not

    @property
    def id(self) -> int:
        return self.row.id

    @property
    def section(self) -> Section:
        try:
            return Section(self.row.section)
        except ValueError:
            return Section.MAINS

    def name(self, language: Language = Language.EN) -> str:
        return self.row.names.get(language) or self.row.names[Language.EN]

    @property
    def missing_names(self) -> list[Language]:
        return [lang for lang in Language if not self.row.names.get(lang)]

    @property
    def confirmed(self) -> bool:
        return self.confirmation is not None

    @property
    def confirmed_allergens(self) -> set[int]:
        return set(self.confirmation.allergens) if self.confirmation else set()

    @property
    def ai_allergens(self) -> set[int]:
        return {
            annex.BY_ID[allergen_id].number
            for suggestion in self.suggestions.values()
            for allergen_id in suggestion.allergens
            if allergen_id in annex.BY_ID
        }

    @property
    def suggested(self) -> set[int]:
        """What the confirmation form starts from: dictionary hits + AI suggestions."""
        return self.analysis.allergens | self.ai_allergens

    @property
    def preselected(self) -> set[int]:
        return self.confirmed_allergens if self.confirmed else self.suggested

    @property
    def drift(self) -> set[int]:
        """Allergens the dictionary is sure about that the confirmation does not list."""
        if not self.confirmation:
            return set()
        return self.analysis.certain - self.confirmed_allergens

    @property
    def to_check(self) -> list[IngredientResult]:
        return self.analysis.to_check

    @property
    def state(self) -> str:
        if self.row.archived:
            return "archived"
        if self.confirmed:
            return "review" if self.drift else "confirmed"
        return "changed" if self.last_confirmation else "new"


class Kitchen:
    def __init__(
        self,
        repo: Repository,
        suggester: Suggester,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self.repo = repo
        self.suggester = suggester
        self.clock = clock

    # Reading

    async def _view(self, row: DishRow, confirmations: dict[int, Confirmation]) -> DishView:
        analysis = analyse(row.recipe)
        keys = {
            item.label: suggestion_key(item.label, row.names[Language.EN])
            for item in analysis.to_check
        }
        cached = await self.repo.get_suggestions(list(keys.values()))
        suggestions = {label: cached[key] for label, key in keys.items() if key in cached}
        confirmation = confirmations.get(row.confirmation_id) if row.confirmation_id else None
        # Belt and braces: a confirmation only counts for the recipe it was made for.
        if confirmation and confirmation.recipe_hash != row.recipe_hash:
            confirmation = None
        mine = [c for c in confirmations.values() if c.dish_id == row.id]
        last = max(mine, key=lambda c: c.id) if mine else None
        return DishView(row, analysis, suggestions, confirmation, last)

    async def dishes(self, include_archived: bool = False) -> list[DishView]:
        rows = await self.repo.list_dishes()
        confirmations = await self.repo.all_confirmations()
        views = [await self._view(row, confirmations) for row in rows]
        if not include_archived:
            views = [v for v in views if not v.row.archived]
        order = list(Section)
        return sorted(views, key=lambda v: (order.index(v.section), v.row.position, v.id))

    async def get(self, dish_id: int) -> DishView | None:
        row = await self.repo.get_dish(dish_id)
        if row is None:
            return None
        confirmations = {c.id: c for c in await self.repo.confirmations(dish_id)}
        return await self._view(row, confirmations)

    async def history(self, dish_id: int) -> tuple[list[Confirmation], list[Event]]:
        return await self.repo.confirmations(dish_id), await self.repo.events(dish_id)

    # Writing

    @staticmethod
    def _clean(names: dict[Language, str], recipe: str, actor: str) -> tuple[str, str]:
        actor = " ".join(actor.split())
        if not actor:
            raise KitchenError("Enter your name: every change is logged with who made it.")
        if not names.get(Language.EN, "").strip():
            raise KitchenError("The dish needs at least an English name.")
        recipe = recipe.strip()
        if not recipe:
            raise KitchenError("List the ingredients, separated by commas or new lines.")
        return actor, recipe

    async def create(
        self, names: dict[Language, str], section: Section, recipe: str, actor: str
    ) -> int:
        actor, recipe = self._clean(names, recipe, actor)
        names = {lang: " ".join(names.get(lang, "").split()) for lang in Language}
        now = self.clock()
        dish_id = await self.repo.add_dish(
            section.value, names, recipe, recipe_hash(recipe), actor, now
        )
        await self.repo.add_event(dish_id, actor, "created", recipe, now)
        await self.repo.commit()
        await self.suggest(dish_id)
        return dish_id

    async def update(
        self,
        dish_id: int,
        names: dict[Language, str],
        section: Section,
        recipe: str,
        actor: str,
    ) -> bool:
        """Save the dish. Returns True if the change reset the confirmation."""
        actor, recipe = self._clean(names, recipe, actor)
        row = await self.repo.get_dish(dish_id)
        if row is None:
            raise KitchenError("No such dish.")
        names = {lang: " ".join(names.get(lang, "").split()) for lang in Language}
        new_hash = recipe_hash(recipe)
        recipe_changed = new_hash != row.recipe_hash
        reset = recipe_changed and row.confirmation_id is not None
        if not recipe_changed and names == row.names and section.value == row.section:
            if recipe != row.recipe:  # only order, spacing or letter case changed
                await self.repo.update_dish(
                    dish_id, section.value, names, recipe, new_hash, actor, self.clock(), False
                )
                await self.repo.commit()
            return False
        now = self.clock()
        await self.repo.update_dish(
            dish_id, section.value, names, recipe, new_hash, actor, now, reset
        )
        if recipe_changed:
            await self.repo.add_event(dish_id, actor, "recipe changed", recipe, now)
        if reset:
            await self.repo.add_event(
                dish_id,
                actor,
                "confirmation reset",
                "The ingredients changed, so the allergens must be confirmed again.",
                now,
            )
        if names != row.names or section.value != row.section:
            await self.repo.add_event(dish_id, actor, "details edited", "names or section", now)
        await self.repo.commit()
        if recipe_changed:
            await self.suggest(dish_id)
        return reset

    async def confirm(
        self,
        dish_id: int,
        allergen_numbers: set[int],
        actor: str,
        expected_hash: str,
        note: str = "",
    ) -> int:
        actor = " ".join(actor.split())
        if not actor:
            raise KitchenError("Enter your name: a confirmation must say who made it.")
        if not allergen_numbers <= set(annex.BY_NUMBER):
            raise KitchenError("Unknown allergen number.")
        row = await self.repo.get_dish(dish_id)
        if row is None:
            raise KitchenError("No such dish.")
        if row.recipe_hash != expected_hash:
            raise StaleRecipeError(
                "The ingredients were changed after you opened this page. Nothing was "
                "confirmed: reload the page, check the new analysis and confirm again."
            )
        now = self.clock()
        confirmation_id = await self.repo.add_confirmation(
            dish_id, row.recipe_hash, row.recipe, sorted(allergen_numbers), actor, now, note
        )
        detail = annex.numbers_label(allergen_numbers) or "none of the 14"
        await self.repo.add_event(dish_id, actor, "confirmed", f"allergens: {detail}", now)
        await self.repo.commit()
        return confirmation_id

    async def set_archived(self, dish_id: int, archived: bool, actor: str) -> None:
        actor = " ".join(actor.split()) or "unknown"
        await self.repo.set_archived(dish_id, archived)
        action = "removed from menu" if archived else "back on menu"
        await self.repo.add_event(dish_id, actor, action, "", self.clock())
        await self.repo.commit()

    async def suggest(self, dish_id: int) -> int:
        """Ask the AI about this dish's ingredients that need a check. Returns how many
        new suggestions were stored. Errors are logged; the chef still sees the items."""
        if not self.suggester.enabled:
            return 0
        row = await self.repo.get_dish(dish_id)
        if row is None:
            return 0
        dish_name = row.names[Language.EN]
        items = analyse(row.recipe).to_check
        keys = {item.label: suggestion_key(item.label, dish_name) for item in items}
        cached = await self.repo.get_suggestions(list(keys.values()))
        missing = [label for label, key in keys.items() if key not in cached]
        if not missing:
            return 0
        try:
            suggestions = await self.suggester.suggest(dish_name, missing)
        except LLMError as exc:
            logger.warning("AI suggestion failed for dish %s: %s", dish_id, exc)
            return 0
        by_text = {fold(s.ingredient).strip(): s for s in suggestions}
        stored = 0
        now = self.clock()
        for position, label in enumerate(missing):
            suggestion = by_text.get(fold(label).strip())
            if suggestion is None and len(suggestions) == len(missing):
                suggestion = suggestions[position]  # same order, slightly different text
            if suggestion is None:
                continue
            ids = [a for a in suggestion.allergens if a in annex.BY_ID]
            await self.repo.save_suggestion(
                keys[label], label, ids, suggestion.reason.strip(), self.suggester.model, now
            )
            stored += 1
        await self.repo.commit()
        return stored
