from pathlib import Path

import pytest

from app.knowledge import KnowledgeBase, KnowledgeBaseError, parse_sections


def test_parse_sections() -> None:
    text = "# Hotel\nintro\n## Pool\nOpen 8-19\n\n## Wi-Fi\nFree\n"
    sections = parse_sections(text)
    assert [s.title for s in sections] == ["Pool", "Wi-Fi"]
    assert sections[0].body == "Open 8-19"


def test_demo_knowledge_base_loads(knowledge: KnowledgeBase) -> None:
    titles = [s.title for s in knowledge.sections]
    assert "Breakfast and meals" in titles
    assert len(titles) >= 10


def test_reload_picks_up_changes(tmp_path: Path) -> None:
    path = tmp_path / "hotel.md"
    path.write_text("## Pool\nOpen 8-19\n", encoding="utf-8")
    kb = KnowledgeBase(path)
    path.write_text("## Pool\nOpen 9-20\n## Spa\nPaid\n", encoding="utf-8")
    assert len(kb.reload().sections) == 2
    assert "9-20" in kb.text


def test_failed_reload_keeps_old_knowledge(tmp_path: Path) -> None:
    path = tmp_path / "hotel.md"
    path.write_text("## Pool\nOpen 8-19\n", encoding="utf-8")
    kb = KnowledgeBase(path)
    path.write_text("oops, someone deleted everything", encoding="utf-8")
    with pytest.raises(KnowledgeBaseError):
        kb.reload()
    assert "8-19" in kb.text


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(KnowledgeBaseError, match="cannot read"):
        KnowledgeBase(tmp_path / "nope.md")
