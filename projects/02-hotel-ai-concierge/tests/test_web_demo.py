"""The in-browser demo adapter (app/web_demo.py), run here with CPython."""

import ast
import json
from pathlib import Path

import pytest

from app import web_demo
from app.language import Language, detect_language
from app.texts import ESCALATED, STAFF_REPLY_HEADER

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG = json.loads((PROJECT_ROOT / "web_demo.json").read_text(encoding="utf-8"))
# Need a thread, a socket or a server: they cannot run in the browser (Pyodide).
NOT_IN_BROWSER = {"aiogram", "aiosqlite", "anthropic", "openai", "fastapi", "uvicorn"}


async def test_start_describes_the_demo() -> None:
    data = await web_demo.start()
    assert data["hotel"] == "Lara Breeze Hotel"
    assert data["provider"] == "mock"
    assert "Wi-Fi" in data["sections"]
    assert [g["telegram_language"] for g in data["guests"]] == ["en", "ru", "tr", "de"]
    guest_ids = {g["id"] for g in data["guests"]}
    assert all(item["guest"] in guest_ids for item in data["script"])
    assert data["staff_answer"]
    assert await web_demo.stats() == {
        "guests": 0,
        "questions": 0,
        "answered_by_bot": 0,
        "escalated": 0,
        "open_escalations": 0,
    }


async def test_welcome_uses_the_telegram_language() -> None:
    await web_demo.start()
    reply = await web_demo.welcome(4)  # Jonas, Telegram in German
    assert reply["language"] == "de"
    assert reply["text"].startswith("Hallo!")


async def test_scripted_conversation() -> None:
    data = await web_demo.start()
    replies = [await web_demo.ask(item["guest"], item["text"]) for item in data["script"]]

    *answered, cake = replies
    assert [r["language"] for r in answered] == ["en", "ru", "tr", "de"]
    assert not any(r["escalated"] for r in answered)
    assert "07:00" in answered[0]["text"]  # breakfast, from the knowledge base
    assert "LaraBreeze_Guest" in answered[1]["text"]
    assert answered[1]["text"].startswith("Из справочника отеля (Wi-Fi")
    assert "08:00" in answered[2]["text"]  # pool hours

    assert cake["escalated"]
    assert cake["text"] == ESCALATED[Language.RU]
    assert cake["staff_message_id"] == 1000
    assert "Question #1 from Иван Петров (@ivan) · Russian" in cake["staff_text"]

    stats = await web_demo.stats()
    assert stats["questions"] == 5
    assert stats["answered_by_bot"] == 4
    assert stats["open_escalations"] == 1


async def test_staff_reply_goes_back_to_the_guest_untranslated_offline() -> None:
    data = await web_demo.start()
    question = await web_demo.ask(2, "Можно заказать торт на день рождения в номер?")
    result = await web_demo.staff_reply(question["staff_message_id"], data["staff_answer"])

    assert result["delivered"]
    assert result["guest"] == 2
    assert result["language"] == "ru"
    assert result["guest_text"] == f"{STAFF_REPLY_HEADER[Language.RU]}\n{data['staff_answer']}"
    assert result["confirmation"] == "✅ Sent to the guest (question #1)"
    # An English reply to a Russian guest needs a translation; the mock model cannot do it.
    assert result["needs_translation"]
    assert not result["translated"]
    assert (await web_demo.stats())["open_escalations"] == 0


async def test_staff_reply_in_the_guest_language_needs_no_translation() -> None:
    await web_demo.start()
    question = await web_demo.ask(2, "Можно заказать торт в номер?")
    result = await web_demo.staff_reply(question["staff_message_id"], "Да, конечно.")
    assert result["delivered"]
    assert not result["needs_translation"]


async def test_staff_reply_to_an_unknown_message() -> None:
    await web_demo.start()
    assert await web_demo.staff_reply(999, "Hello") == {"delivered": False}


async def test_suggestions_are_in_their_language_and_some_go_to_staff() -> None:
    data = await web_demo.start()
    outcomes = []
    for item in data["suggestions"]:
        assert detect_language(item["text"]) == item["lang"], item["text"]
        reply = await web_demo.ask(1, item["text"])
        assert reply["language"] == item["lang"]
        outcomes.append(reply["escalated"])
    assert True in outcomes
    assert False in outcomes


async def test_start_resets_the_conversation() -> None:
    await web_demo.start()
    await web_demo.ask(1, "What time is breakfast?")
    await web_demo.start()
    assert (await web_demo.stats())["questions"] == 0


async def test_empty_message_is_rejected() -> None:
    await web_demo.start()
    with pytest.raises(ValueError):
        await web_demo.ask(1, "   ")
    with pytest.raises(ValueError):
        await web_demo.staff_reply(1000, "")


async def test_long_message_is_cut() -> None:
    await web_demo.start()
    reply = await web_demo.ask(1, "breakfast " * 500)
    assert not reply["escalated"]


def _module_files(module: str) -> list[str]:
    """The files Python runs for `import module`: each package's __init__.py, then the module."""
    parts = module.split(".")
    files = []
    for i in range(1, len(parts) + 1):
        path = "/".join(parts[:i])
        files.append(f"{path}/__init__.py" if (PROJECT_ROOT / path).is_dir() else f"{path}.py")
    return files


def _module_level_imports(path: Path) -> set[str]:
    """Imports that run when the module is loaded (not inside functions or TYPE_CHECKING)."""
    names: set[str] = set()
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            if node.module == "app":  # "from app import texts" imports app/texts.py
                names.update(f"app.{alias.name}" for alias in node.names)
    return names


def test_web_demo_json_lists_exactly_the_modules_the_demo_imports() -> None:
    files = set(CONFIG["files"])
    assert CONFIG["entry"] == "app.web_demo"
    assert all((PROJECT_ROOT / f).is_file() for f in files)
    assert "knowledge/hotel.md" in files
    assert ".env" not in files

    reached: set[str] = set()
    todo = _module_files(CONFIG["entry"])
    while todo:
        current = todo.pop()
        if current in reached:
            continue
        reached.add(current)
        assert current in files, f"{current} is imported by the demo but not in web_demo.json"
        for module in _module_level_imports(PROJECT_ROOT / current):
            root = module.split(".")[0]
            assert root not in NOT_IN_BROWSER, f"{current} imports {module} at module level"
            if root == "app":
                todo.extend(_module_files(module))

    # create_llm() imports the mock provider when it is called, not at module level.
    assert {f for f in files if f.endswith(".py")} == reached | {"app/llm/mock.py"}
