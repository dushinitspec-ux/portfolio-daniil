"""Web UI for the kitchen (dish list, recipe editor, confirmation) and the printable menu.

Plain HTML forms with POST-redirect-GET: no JavaScript is needed to use it.
There is no login: names are typed, not authenticated. Run it on the kitchen's own
network or behind the business's existing login/VPN (see README, Limitations).
"""

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app import allergens as annex
from app.i18n import Language, Section, parse_language
from app.matcher import analyse
from app.menu import build_menu, menu_json
from app.service import DishView, Kitchen, KitchenError, StaleRecipeError

TEMPLATES = Jinja2Templates(directory=Path(__file__).parent / "templates")
NAME_COOKIE = "chef_name"

STATE_ORDER = {"changed": 0, "new": 1, "review": 2, "confirmed": 3, "archived": 4}
STATE_LABELS = {
    "confirmed": "Confirmed",
    "review": "Confirmed · review",
    "changed": "Recipe changed",
    "new": "Not confirmed",
    "archived": "Off the menu",
}


class CheckRequest(BaseModel):
    ingredients: str


def _names(en: str, ru: str, tr: str, de: str) -> dict[Language, str]:
    return {Language.EN: en, Language.RU: ru, Language.TR: tr, Language.DE: de}


def _section(value: str) -> Section:
    try:
        return Section(value)
    except ValueError:
        raise HTTPException(400, f"unknown section {value!r}") from None


def _when(value: datetime, tz: ZoneInfo) -> str:
    return value.astimezone(tz).strftime("%d %b %Y, %H:%M")


def create_app(
    kitchen: Kitchen,
    *,
    title: str,
    tz: ZoneInfo,
    demo: bool = False,
    clock: Callable[[], datetime] | None = None,
) -> FastAPI:
    app = FastAPI(title="Allergen Labels", version="0.1.0")
    now = clock or kitchen.clock

    def base(request: Request, **extra: Any) -> dict[str, Any]:
        return {
            "demo": demo,
            "title": title,
            "ai_enabled": kitchen.suggester.enabled,
            "ai_model": kitchen.suggester.model,
            "allergens": annex.ALLERGENS,
            "by_number": annex.BY_NUMBER,
            "by_id": annex.BY_ID,
            "languages": list(Language),
            "EN": Language.EN,
            "sections": list(Section),
            "state_labels": STATE_LABELS,
            "chef_name": request.cookies.get(NAME_COOKIE, ""),
            "when": lambda value: _when(value, tz),
            **extra,
        }

    def remember(response: Response, actor: str) -> Response:
        response.set_cookie(NAME_COOKIE, actor.strip()[:80], max_age=60 * 60 * 24 * 180)
        return response

    async def dish_page(
        request: Request,
        view: DishView | None,
        status_code: int = 200,
        error: str = "",
        form: dict[str, Any] | None = None,
    ) -> HTMLResponse:
        confirmations, events = await kitchen.history(view.id) if view else ([], [])
        context = base(
            request,
            view=view,
            error=error,
            form=form or {},
            confirmations=confirmations,
            events=events,
            saved=request.query_params.get("saved", ""),
        )
        return TEMPLATES.TemplateResponse(request, "dish.html", context, status_code=status_code)

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        dishes = await kitchen.dishes(include_archived=True)
        active = [d for d in dishes if not d.row.archived]
        counts = {
            "total": len(active),
            "published": sum(d.confirmed for d in active),
            "waiting": sum(not d.confirmed for d in active),
            "review": sum(bool(d.drift) for d in active),
        }
        # What needs a person comes first; the menu order is kept within each group.
        dishes.sort(key=lambda d: STATE_ORDER[d.state])
        context = base(request, dishes=dishes, counts=counts)
        return TEMPLATES.TemplateResponse(request, "index.html", context)

    @app.get("/dishes/new", response_class=HTMLResponse)
    async def new_dish(request: Request) -> HTMLResponse:
        return await dish_page(request, None)

    @app.post("/dishes")
    async def create_dish(
        request: Request,
        name_en: Annotated[str, Form()] = "",
        name_ru: Annotated[str, Form()] = "",
        name_tr: Annotated[str, Form()] = "",
        name_de: Annotated[str, Form()] = "",
        section: Annotated[str, Form()] = Section.MAINS.value,
        recipe: Annotated[str, Form()] = "",
        actor: Annotated[str, Form()] = "",
    ) -> Response:
        try:
            dish_id = await kitchen.create(
                _names(name_en, name_ru, name_tr, name_de), _section(section), recipe, actor
            )
        except KitchenError as exc:
            form = {
                "names": _names(name_en, name_ru, name_tr, name_de),
                "recipe": recipe,
                "section": section,
            }
            return await dish_page(request, None, 400, str(exc), form)
        response = RedirectResponse(f"/dishes/{dish_id}?saved=created", status_code=303)
        return remember(response, actor)

    @app.get("/dishes/{dish_id}", response_class=HTMLResponse)
    async def show_dish(request: Request, dish_id: int) -> HTMLResponse:
        view = await kitchen.get(dish_id)
        if view is None:
            raise HTTPException(404, "No such dish")
        return await dish_page(request, view)

    @app.post("/dishes/{dish_id}")
    async def update_dish(
        request: Request,
        dish_id: int,
        name_en: Annotated[str, Form()] = "",
        name_ru: Annotated[str, Form()] = "",
        name_tr: Annotated[str, Form()] = "",
        name_de: Annotated[str, Form()] = "",
        section: Annotated[str, Form()] = Section.MAINS.value,
        recipe: Annotated[str, Form()] = "",
        actor: Annotated[str, Form()] = "",
    ) -> Response:
        try:
            reset = await kitchen.update(
                dish_id,
                _names(name_en, name_ru, name_tr, name_de),
                _section(section),
                recipe,
                actor,
            )
        except KitchenError as exc:
            view = await kitchen.get(dish_id)
            if view is None:
                raise HTTPException(404, "No such dish") from None
            form = {
                "names": _names(name_en, name_ru, name_tr, name_de),
                "recipe": recipe,
                "section": section,
            }
            return await dish_page(request, view, 400, str(exc), form)
        flag = "reset" if reset else "saved"
        response = RedirectResponse(f"/dishes/{dish_id}?saved={flag}", status_code=303)
        return remember(response, actor)

    @app.post("/dishes/{dish_id}/confirm")
    async def confirm_dish(
        request: Request,
        dish_id: int,
        recipe_hash: Annotated[str, Form()],
        actor: Annotated[str, Form()] = "",
        note: Annotated[str, Form()] = "",
        allergen: Annotated[list[int] | None, Form()] = None,
    ) -> Response:
        try:
            await kitchen.confirm(dish_id, set(allergen or []), actor, recipe_hash, note.strip())
        except KitchenError as exc:
            view = await kitchen.get(dish_id)
            if view is None:
                raise HTTPException(404, "No such dish") from None
            code = 409 if isinstance(exc, StaleRecipeError) else 400
            return await dish_page(request, view, code, str(exc))
        response = RedirectResponse(f"/dishes/{dish_id}?saved=confirmed", status_code=303)
        return remember(response, actor)

    @app.post("/dishes/{dish_id}/archive")
    async def archive_dish(
        dish_id: int, actor: Annotated[str, Form()] = "", restore: Annotated[str, Form()] = ""
    ) -> Response:
        if await kitchen.get(dish_id) is None:
            raise HTTPException(404, "No such dish")
        await kitchen.set_archived(dish_id, not restore, actor)
        return RedirectResponse(f"/dishes/{dish_id}", status_code=303)

    @app.get("/menu", response_class=HTMLResponse)
    async def menu(request: Request, lang: str = "en") -> HTMLResponse:
        language = parse_language(lang)
        view = build_menu(await kitchen.dishes(), language, title, tz, demo)
        return TEMPLATES.TemplateResponse(request, "menu.html", base(request, menu=view))

    @app.get("/api/menu.json")
    async def api_menu(lang: str | None = None) -> JSONResponse:
        language = parse_language(lang) if lang else None
        data = menu_json(await kitchen.dishes(), title, now(), language)
        return JSONResponse(data, headers={"Content-Disposition": "inline; filename=menu.json"})

    @app.get("/api/dishes")
    async def api_dishes() -> list[dict[str, Any]]:
        return [
            {
                "id": d.id,
                "section": d.section.value,
                "names": {lang.value: d.row.names[lang] for lang in Language},
                "recipe": d.row.recipe,
                "state": d.state,
                "published": d.confirmed and not d.row.archived,
                "confirmed_allergens": sorted(d.confirmed_allergens) if d.confirmed else None,
                "suggested_allergens": sorted(d.suggested),
                "needs_check": [i.label for i in d.to_check],
                "analysis": d.analysis.model_dump(mode="json"),
            }
            for d in await kitchen.dishes(include_archived=True)
        ]

    @app.post("/api/check")
    async def api_check(body: CheckRequest) -> dict[str, Any]:
        """Dictionary analysis of an ingredient list, without saving anything."""
        result = analyse(body.ingredients)
        return {
            "allergens": [
                {"number": n, "id": annex.BY_NUMBER[n].id, "certain": n in result.certain}
                for n in sorted(result.allergens)
            ],
            "needs_check": [i.label for i in result.to_check],
            "items": result.model_dump(mode="json")["items"],
        }

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app
