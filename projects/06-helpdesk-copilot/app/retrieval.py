"""BM25 search over knowledge-base sections, with a confidence check.

BM25 is the classic ranking function of search engines (Lucene, Elasticsearch): a word counts
more if it is rare in the knowledge base (IDF) and if it appears in a short section rather
than a long one. It needs no model, runs in microseconds and is easy to explain, which suits
a knowledge base of a few dozen pages.

BM25 always returns *something*, even for "the coffee machine is leaking". The confidence
check decides whether the best section really covers the question: the share of the
question's information (IDF-weighted) that the best section contains.
"""

import math
from collections import Counter
from dataclasses import dataclass, field

from app.knowledge import Document, Section
from app.text import analyze, analyze_groups


@dataclass(frozen=True)
class RetrievalOptions:
    """Switches for the evaluation's ablation table; the defaults are what the app uses."""

    headings: bool = True  # index the document title and section heading with the text
    stemming: bool = True
    glossary: bool = True  # German/Russian/Turkish words and suffixes -> English terms
    synonyms: bool = True  # chat words -> knowledge-base words ("log in" -> "sign in")
    k1: float = 1.2
    b: float = 0.75


class BM25:
    """Okapi BM25 over pre-tokenized texts."""

    def __init__(self, corpus: list[list[str]], k1: float = 1.2, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self.n = len(corpus)
        self.lengths = [len(tokens) for tokens in corpus]
        self.avg_length = sum(self.lengths) / self.n if self.n else 0.0
        self.term_counts = [Counter(tokens) for tokens in corpus]
        df: Counter[str] = Counter()
        for counts in self.term_counts:
            df.update(counts.keys())
        self.df = df

    def idf(self, term: str) -> float:
        # The "+1" variant (Lucene) is never negative, even for a word in every section.
        df = self.df.get(term, 0)
        return math.log(1 + (self.n - df + 0.5) / (df + 0.5))

    def score(self, query: list[str], index: int) -> float:
        counts = self.term_counts[index]
        norm = self.k1 * (1 - self.b + self.b * self.lengths[index] / self.avg_length)
        total = 0.0
        for term in set(query):
            tf = counts.get(term, 0)
            if tf:
                total += self.idf(term) * tf * (self.k1 + 1) / (tf + norm)
        return total

    def scores(self, query: list[str]) -> list[float]:
        return [self.score(query, i) for i in range(self.n)]


@dataclass(frozen=True)
class Hit:
    section: Section
    score: float
    matched: tuple[str, ...]


@dataclass(frozen=True)
class Retrieval:
    question: str
    terms: tuple[str, ...]
    hits: list[Hit]
    coverage: float  # 0..1: share of the question's IDF weight found in the best section
    confident: bool

    @property
    def top(self) -> Hit | None:
        return self.hits[0] if self.hits else None

    @property
    def coverage_label(self) -> str:
        """Two decimals rounded down, so a failing 0.298 is never shown as "0.30"."""
        return f"{math.floor(self.coverage * 100) / 100:.2f}"


@dataclass
class Retriever:
    documents: list[Document]
    options: RetrievalOptions = field(default_factory=RetrievalOptions)
    min_score: float = 3.0
    min_coverage: float = 0.5

    def __post_init__(self) -> None:
        self.sections = [s for doc in self.documents for s in doc.sections]
        corpus = [self._index_terms(s) for s in self.sections]
        self.vocabulary = frozenset(term for tokens in corpus for term in tokens)
        self.bm25 = BM25(corpus, self.options.k1, self.options.b)

    def _index_terms(self, section: Section) -> list[str]:
        text = section.text
        if self.options.headings:
            text = f"{section.doc_title}\n{section.heading}\n{text}"
        return analyze(text, stemming=self.options.stemming, glossary=False, synonyms=False)

    def query_groups(self, question: str) -> list[tuple[str, ...]]:
        """One group of alternative terms per word of the question."""
        groups = analyze_groups(
            question,
            stemming=self.options.stemming,
            glossary=self.options.glossary,
            synonyms=self.options.synonyms,
            vocabulary=self.vocabulary,
        )
        return list(dict.fromkeys(groups))

    def search(self, question: str, k: int = 4) -> Retrieval:
        groups = self.query_groups(question)
        terms = list(dict.fromkeys(term for group in groups for term in group))
        if not terms:
            return Retrieval(question, (), [], 0.0, False)

        scores = self.bm25.scores(terms)
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        hits = [
            Hit(
                self.sections[i],
                scores[i],
                tuple(t for t in terms if t in self.bm25.term_counts[i]),
            )
            for i in ranked[:k]
            if scores[i] > 0
        ]
        coverage = self.coverage(groups, hits[0]) if hits else 0.0
        confident = bool(hits) and hits[0].score >= self.min_score
        confident = confident and coverage >= self.min_coverage
        return Retrieval(question, tuple(terms), hits, coverage, confident)

    def coverage(self, groups: list[tuple[str, ...]], hit: Hit) -> float:
        """IDF-weighted share of the question's words that the section contains.

        A word counts as found if any of its alternatives is in the section; its weight is
        the IDF of its rarest alternative. Words the knowledge base has never seen get the
        highest IDF, so "coffee machine" questions score low even if "machine" matched.
        """
        matched = set(hit.matched)
        total = found = 0.0
        for group in groups:
            weight = max(self.bm25.idf(t) for t in group)
            total += weight
            if matched.intersection(group):
                found += weight
        return found / total if total else 0.0
