import pytest

from app.knowledge import parse_document
from app.retrieval import BM25, Retriever


def test_bm25_rare_words_weigh_more() -> None:
    bm25 = BM25([["printer", "toner"], ["printer", "paper"], ["printer", "scan"]])
    assert bm25.idf("toner") > bm25.idf("printer") > 0
    assert bm25.score(["toner"], 0) > bm25.score(["printer"], 0)


def test_bm25_repeated_word_saturates() -> None:
    bm25 = BM25([["vpn"], ["vpn"] * 2, ["vpn"] * 20, ["other"]], b=0)
    one, two, twenty = (bm25.score(["vpn"], i) for i in range(3))
    assert one < two < twenty
    assert twenty < one * (bm25.k1 + 1)  # the limit of the tf part is k1 + 1 times one hit


def test_bm25_short_section_beats_long_one_with_the_same_hit() -> None:
    bm25 = BM25([["mfa", "phone"], ["mfa"] + ["filler"] * 30])
    assert bm25.score(["mfa"], 0) > bm25.score(["mfa"], 1)


@pytest.mark.parametrize(
    ("question", "doc_id"),
    [
        ("How do I reset a forgotten password?", "password-reset"),
        ("Wie lautet das WLAN-Passwort für Gäste?", "guest-wifi"),
        ("WireGuard has no handshake", "vpn"),
        ("Как настроить приложение Authenticator?", "mfa"),
        ("OneDrive'da bir dosyayı yanlışlıkla sildim", "backup-restore"),
    ],
)
def test_best_section_comes_from_the_right_document(
    retriever: Retriever, question: str, doc_id: str
) -> None:
    result = retriever.search(question, k=3)
    assert result.top is not None
    assert result.top.section.doc_id == doc_id
    assert result.confident


def test_search_returns_k_hits_with_ids_and_matched_terms(retriever: Retriever) -> None:
    result = retriever.search("printer paper jam", k=4)
    assert len(result.hits) == 4
    assert result.hits[0].section.id == "printer#paper-jam-toner-and-paper"
    assert set(result.hits[0].matched) == {"printer", "paper", "jam"}
    scores = [h.score for h in result.hits]
    assert scores == sorted(scores, reverse=True)


def test_out_of_scope_question_is_not_confident(retriever: Retriever) -> None:
    result = retriever.search("The coffee machine in the kitchen is leaking")
    assert not result.confident
    assert result.coverage < 0.3


def test_question_without_content_words(retriever: Retriever) -> None:
    result = retriever.search("Hi! Could you please?")
    assert result.hits == []
    assert not result.confident


def test_coverage_counts_a_synonym_group_once() -> None:
    doc = parse_document("signin", "# Sign in\n\n## How\n\nSign in with your company account.\n")
    retriever = Retriever([doc], min_score=0, min_coverage=0.5)
    # "log" is not in the text, its synonym "sign" is: the word counts as found.
    result = retriever.search("log account")
    assert result.coverage == pytest.approx(1.0)
