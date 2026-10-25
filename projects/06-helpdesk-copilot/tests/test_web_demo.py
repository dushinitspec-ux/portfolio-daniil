"""The in-browser demo adapter (app/web_demo.py), run here with CPython."""

import ast
import json
from pathlib import Path

import pytest

from app import messages, web_demo
from app.config import Settings

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG = json.loads((PROJECT_ROOT / "web_demo.json").read_text(encoding="utf-8"))
# Need a thread, a socket or a server: they cannot run in the browser (Pyodide).
NOT_IN_BROWSER = {"aiogram", "aiosqlite", "anthropic", "fastapi", "uvicorn", "jinja2"}


def test_demo_settings_are_the_validated_defaults() -> None:
    validated = Settings(_env_file=None, demo_mode=True)  # type: ignore[call-arg]
    assert web_demo.demo_settings().model_dump() == validated.model_dump()


async def test_start_describes_the_demo() -> None:
    data = await web_demo.start()
    assert data["company"] == "Sample Office"
    assert data["answers_by"] == "demo (extractive)"
    assert (data["min_score"], data["min_coverage"], data["top_k"]) == (2.0, 0.3, 4)
    assert data["documents"] == 15  # knowledge/*.md without README.md
    assert len(data["script"]) == 4
    assert "/ticket The scanner is offline" in data["suggestions"]
    assert not {item["question"] for item in data["script"]} & set(data["suggestions"])
    assert await web_demo.tickets() == []


async def test_start_command_shows_the_ai_notice() -> None:
    await web_demo.start()
    reply = await web_demo.send("/start")
    assert reply["kind"] == "text"
    assert reply["text"].startswith("Hi Erika!")
    assert "I'm an AI system, not a person." in reply["text"]


async def test_answer_with_numbered_sources() -> None:
    await web_demo.start()
    reply = await web_demo.send("  How do I connect to the VPN from home?\n")
    assert reply["kind"] == "answer"
    assert reply["question"] == "How do I connect to the VPN from home?"
    assert reply["answered"]
    assert reply["buttons"]
    assert reply["answer"].endswith("[1]")
    assert reply["sources"] == [
        {"number": 1, "label": "VPN for remote work", "file": "knowledge/vpn.md"}
    ]
    assert "Sources:\n[1] VPN for remote work" in reply["text"]
    retrieval = reply["retrieval"]
    assert retrieval["confident"]
    assert retrieval["coverage"] == 1.0
    assert retrieval["hits"][0]["file"] == "knowledge/vpn.md"
    assert set(retrieval["hits"][0]["matched"]) == {"connect", "vpn", "hom"}
    assert len(retrieval["hits"]) <= 4
    assert reply["ticket"] is None


async def test_russian_question_finds_the_english_section() -> None:
    await web_demo.start()
    reply = await web_demo.send("Принтер не печатает, документ висит в очереди")
    assert reply["answered"]
    assert reply["sources"][0]["label"].endswith("Print job is stuck in the queue")
    assert "printer" in reply["retrieval"]["terms"]


async def test_security_incident_is_answered_and_gets_a_p1_ticket() -> None:
    await web_demo.start()
    reply = await web_demo.send("I clicked a link in a fake DHL email and typed my password")
    assert reply["answered"]
    assert not reply["buttons"]  # the ticket is already open
    assert reply["route"] == "SECURITY"
    assert reply["ticket"]["priority"] == "P1"
    assert reply["ticket"]["category"] == "security"
    assert "security incident" in reply["text"]
    assert reply["it_notification"].startswith("🎫 New Ticket #1 · P1 · security")


async def test_question_below_the_threshold_becomes_a_ticket() -> None:
    await web_demo.start()
    reply = await web_demo.send("The coffee machine in the kitchen is leaking")
    assert not reply["answered"]
    assert reply["route"] == "NOT_FOUND"
    assert not reply["retrieval"]["confident"]
    assert reply["retrieval"]["coverage"] < 0.3
    assert reply["ticket_reason"].startswith("not found in the knowledge base (coverage 0.20")
    assert reply["ticket"]["priority"] == "P3"
    assert reply["text"].startswith("I couldn't find this in the IT knowledge base")


async def test_scripted_run_fills_the_queue_in_priority_order() -> None:
    data = await web_demo.start()
    for item in data["script"]:
        reply = await web_demo.send(item["question"])
        if item["then"] == "solved":
            assert (await web_demo.solved(reply["question_id"]))["text"] == messages.SOLVED
    queue = await web_demo.tickets()
    assert [t["priority"] for t in queue] == ["P1", "P3"]
    stats = await web_demo.stats()
    assert stats["questions"] == 4
    assert stats["answered"] == 3
    assert stats["solved"] == 1
    assert stats["open_by_priority"]["P1"] == 1


async def test_create_ticket_button() -> None:
    await web_demo.start()
    reply = await web_demo.send("How do I add the colour printer?")
    result = await web_demo.create_ticket(reply["question_id"])
    assert result["ok"]
    assert result["text"].startswith("Sorry the answer didn't help.")
    assert result["ticket"]["route_reason"] == "the answer did not help (employee asked)"
    again = await web_demo.create_ticket(reply["question_id"])  # pressed twice: same ticket
    assert again["ticket"]["id"] == result["ticket"]["id"]
    assert len(await web_demo.tickets()) == 1


async def test_buttons_on_an_unknown_question() -> None:
    await web_demo.start()
    assert await web_demo.solved(99) == {"ok": False, "text": messages.NOT_YOURS}
    assert (await web_demo.create_ticket(99))["ok"] is False


async def test_ticket_command() -> None:
    await web_demo.start()
    usage = await web_demo.send("/ticket")
    assert usage == {"kind": "text", "text": messages.TICKET_USAGE}
    reply = await web_demo.send("/ticket The scanner is offline")
    assert reply["kind"] == "ticket"
    assert reply["ticket"]["route_reason"] == "written as a ticket"
    assert reply["text"].startswith("Thanks, I passed it on to IT.")


async def test_other_commands_show_the_welcome() -> None:
    await web_demo.start()
    assert (await web_demo.send("/help"))["text"].startswith("Hi Erika!")


async def test_start_resets_the_chat() -> None:
    await web_demo.start()
    await web_demo.send("The whole office has no internet!")
    await web_demo.start()
    assert await web_demo.tickets() == []
    assert (await web_demo.stats())["questions"] == 0


async def test_empty_message_is_rejected() -> None:
    await web_demo.start()
    with pytest.raises(ValueError):
        await web_demo.send("  ")


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
            if node.module == "app":  # "from app import messages" imports app/messages.py
                names.update(f"app.{alias.name}" for alias in node.names)
    return names


def test_web_demo_json_lists_exactly_the_modules_the_demo_imports() -> None:
    files = set(CONFIG["files"])
    assert CONFIG["entry"] == "app.web_demo"
    assert "knowledge/*.md" in files
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

    # create_llm() imports the demo provider when it is called, not at module level.
    assert {f for f in files if f.endswith(".py")} == reached | {"app/llm/demo.py"}
