import pytest

from app.knowledge import KnowledgeBase
from app.language import Language
from app.llm.mock import MockLLM


@pytest.mark.parametrize(
    ("question", "language", "section"),
    [
        ("What time is breakfast?", Language.EN, "Breakfast and meals"),
        ("Какой пароль от вайфая?", Language.RU, "Wi-Fi"),
        ("Havuz saat kaçta açılıyor?", Language.TR, "Pools and beach"),
        ("Gibt es einen Parkplatz?", Language.DE, "Parking"),
        ("Можно с собакой?", Language.RU, "Pets"),
    ],
)
async def test_finds_section_in_any_language(
    knowledge: KnowledgeBase, question: str, language: Language, section: str
) -> None:
    result = await MockLLM().answer(question, language, knowledge.text, "")
    assert result.found_in_knowledge_base
    assert f"({section}" in result.answer


async def test_unknown_question_is_not_found(knowledge: KnowledgeBase) -> None:
    result = await MockLLM().answer("Can I bring my drone?", Language.EN, knowledge.text, "")
    assert not result.found_in_knowledge_base
    assert result.answer == ""


async def test_keywords_match_whole_word_starts(knowledge: KnowledgeBase) -> None:
    # "pet" must not match inside "carpet".
    result = await MockLLM().answer("The carpet is dirty", Language.EN, knowledge.text, "")
    assert "(Pets" not in result.answer
