from app.citations import Source, check_citations, cited_numbers, format_sources, number_sources
from app.knowledge import Document


def sources(documents: list[Document]) -> list[Source]:
    by_id = {d.id: d for d in documents}
    return number_sources([by_id["vpn"].sections[1], by_id["wifi"].sections[0]])


def test_numbers_are_parsed_in_every_style() -> None:
    assert cited_numbers("Open WireGuard [1]. Then [2][1], or [3, 1].") == [1, 2, 3]
    assert cited_numbers("No citations here.") == []


def test_sources_are_numbered_from_one(documents: list[Document]) -> None:
    numbered = sources(documents)
    assert [s.number for s in numbered] == [1, 2]
    assert format_sources(numbered).splitlines() == [
        "[1] VPN for remote work › Install the VPN client",
        "[2] Office Wi-Fi",
    ]


def test_citations_map_to_document_titles(documents: list[Document]) -> None:
    check = check_citations("Install WireGuard [1]. Connect to SO-Staff [2].", sources(documents))
    assert check.grounded
    assert [s.section.doc_title for s in check.cited] == ["VPN for remote work", "Office Wi-Fi"]
    assert check.unknown == []


def test_unknown_citation_is_removed(documents: list[Document]) -> None:
    check = check_citations("Install WireGuard [1][7]. Call extension 999 [9].", sources(documents))
    assert check.unknown == [7, 9]
    assert check.text == "Install WireGuard [1]. Call extension 999."
    assert [s.number for s in check.cited] == [1]


def test_answer_without_valid_citation_is_not_grounded(documents: list[Document]) -> None:
    assert not check_citations("Restart your router.", sources(documents)).grounded
    assert not check_citations("Restart your router [5].", sources(documents)).grounded
