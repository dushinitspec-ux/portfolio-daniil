"""The published menu: only confirmed dishes, with allergen numbers and the legend."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.allergens import ALLERGENS, BY_NUMBER
from app.i18n import Language, Section, menu_text
from app.service import DishView


@dataclass(frozen=True)
class MenuDish:
    id: int
    name: str
    allergens: tuple[int, ...]
    translated: bool  # False: the name is shown in English because a translation is missing


@dataclass(frozen=True)
class MenuSection:
    section: Section
    title: str
    dishes: list[MenuDish]


@dataclass(frozen=True)
class LegendLine:
    number: int
    label: str
    name: str

    @property
    def detail(self) -> str:
        """The official wording without repeating the label: "Nuts: almonds, ..." -> "almonds,
        ..."; empty when the wording is just the label ("Eggs")."""
        rest = self.name[len(self.label) :]
        # Only "Label: ..." or "Label (...)": "Glutenhaltiges Getreide" and "Gluten içeren
        # tahıllar" must stay whole.
        if self.name.startswith(self.label) and (not rest or rest.startswith((":", " ("))):
            return rest.lstrip(": ")
        return self.name


@dataclass(frozen=True)
class MenuView:
    language: Language
    title: str
    sections: list[MenuSection]
    legend: list[LegendLine]
    last_checked: str
    hidden: list[str]  # dishes left out because they are not confirmed (staff only)
    demo: bool

    def text(self, key: str, **values: str) -> str:
        return menu_text(key, self.language, **values)


def published(dishes: list[DishView]) -> list[DishView]:
    return [d for d in dishes if d.confirmed and not d.row.archived]


def build_menu(
    dishes: list[DishView],
    language: Language,
    title: str,
    tz: ZoneInfo,
    demo: bool = False,
) -> MenuView:
    shown = published(dishes)
    sections = []
    for section in Section:
        in_section = [
            MenuDish(
                id=d.id,
                name=d.name(language),
                allergens=tuple(sorted(d.confirmed_allergens)),
                translated=bool(d.row.names.get(language)),
            )
            for d in shown
            if d.section is section
        ]
        if in_section:
            sections.append(MenuSection(section, section.label(language), in_section))
    legend = [LegendLine(a.number, a.label(language), a.name(language)) for a in ALLERGENS]
    times = [d.confirmation.confirmed_at for d in shown if d.confirmation]
    last = max(times).astimezone(tz).strftime("%d.%m.%Y") if times else "—"
    hidden = [d.name(Language.EN) for d in dishes if not d.confirmed and not d.row.archived]
    return MenuView(language, title, sections, legend, last, hidden, demo)


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def menu_json(
    dishes: list[DishView], title: str, now: datetime, language: Language | None = None
) -> dict[str, Any]:
    """Machine-readable export of the published menu, for a website or a POS system."""
    languages = [language] if language else list(Language)

    def names(source: dict[Language, str]) -> dict[str, str]:
        return {lang.value: source[lang] for lang in languages}

    shown = published(dishes)
    return {
        "restaurant": title,
        "generated_at": _iso(now),
        "regulation": "Regulation (EU) No 1169/2011, Annex II",
        "languages": [lang.value for lang in languages],
        "legend": [
            {
                "number": a.number,
                "id": a.id,
                "label": names(a.short),
                "name": names(a.names),
            }
            for a in ALLERGENS
        ],
        "dishes": [
            {
                "id": d.id,
                "section": d.section.value,
                "name": {lang.value: d.name(lang) for lang in languages},
                "allergens": sorted(d.confirmed_allergens),
                "allergen_ids": [BY_NUMBER[n].id for n in sorted(d.confirmed_allergens)],
                "confirmed_by": d.confirmation.confirmed_by if d.confirmation else None,
                "confirmed_at": _iso(d.confirmation.confirmed_at) if d.confirmation else None,
            }
            for d in shown
        ],
        "not_published": [
            {"id": d.id, "name": d.name(Language.EN), "reason": "allergens not confirmed"}
            for d in dishes
            if not d.confirmed and not d.row.archived
        ],
    }
