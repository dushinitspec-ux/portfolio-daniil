"""Evaluation: does retrieval find the right document, and does the copilot route correctly?

    uv run python -m app eval              # dev set: retrieval, routing, citations
    uv run python -m app eval --ablation   # what each retrieval step adds
    uv run python -m app eval --holdout    # the held-out questions
    uv run python -m app eval --llm        # answers from Claude instead of the extractive
                                           # demo answerer (needs ANTHROPIC_API_KEY, costs money)

Metrics:
- hit@k: the expected document is among the documents of the top-k retrieved sections.
- answered: the copilot answers instead of opening a ticket.
- citation correct: an answered question cites a section of the expected document.
- out-of-scope routed: a question the knowledge base cannot answer becomes a ticket.
"""

import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from app.copilot import Copilot
from app.db import Repository
from app.knowledge import Document
from app.llm import LLMClient
from app.retrieval import RetrievalOptions, Retriever

K = 3

ABLATION_STEPS: list[tuple[str, RetrievalOptions]] = [
    ("BM25 on section text", RetrievalOptions(False, False, False, False)),
    ("+ title and heading", RetrievalOptions(True, False, False, False)),
    ("+ English stemming", RetrievalOptions(True, True, False, False)),
    ("+ DE/RU/TR glossary", RetrievalOptions(True, True, True, False)),
    ("+ chat synonyms", RetrievalOptions(True, True, True, True)),
]


@dataclass(frozen=True)
class Item:
    question: str
    expected: str | None  # None = out of scope
    lang: str


@dataclass(frozen=True)
class Result:
    item: Item
    rank: int | None  # 1-based rank of the first section from the expected document
    top_docs: list[str]
    coverage: float
    answered: bool
    cited_docs: list[str]
    why_ticket: str

    def hit(self, k: int) -> bool:
        return self.rank is not None and self.rank <= k

    @property
    def citation_correct(self) -> bool:
        return self.item.expected in self.cited_docs


def load_items(path: Path, section: str) -> list[Item]:
    data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [Item(e["q"], e.get("expected"), e.get("lang", "en")) for e in data.get(section) or []]


async def evaluate(copilot: Copilot, items: list[Item]) -> list[Result]:
    results = []
    for item in items:
        reply = await copilot.preview(item.question)
        decision = reply.decision
        docs = [hit.section.doc_id for hit in decision.retrieval.hits[:K]]
        rank = docs.index(item.expected) + 1 if item.expected in docs else None
        results.append(
            Result(
                item,
                rank,
                docs,
                decision.retrieval.coverage,
                reply.answered,
                [s.section.doc_id for s in decision.sources],
                decision.ticket_reason,
            )
        )
    return results


def pct(part: int, whole: int) -> str:
    return f"{part}/{whole} ({100 * part / whole:.1f} %)" if whole else "-"


def retrieval_lines(results: list[Result]) -> list[str]:
    n = len(results)
    lines = [
        f"  hit@1  {pct(sum(r.hit(1) for r in results), n)}",
        f"  hit@3  {pct(sum(r.hit(3) for r in results), n)}",
    ]
    by_lang: dict[str, list[Result]] = defaultdict(list)
    for r in results:
        by_lang[r.item.lang].append(r)
    if len(by_lang) > 1:
        parts = [
            f"{lang} {sum(r.hit(1) for r in rs)}/{len(rs)}" for lang, rs in sorted(by_lang.items())
        ]
        lines.append("  hit@1 by language: " + ", ".join(parts))
    return lines


def routing_lines(in_scope: list[Result], out_of_scope: list[Result]) -> list[str]:
    answered = [r for r in in_scope if r.answered]
    lines = [
        f"  in-scope answered (not a ticket)   {pct(len(answered), len(in_scope))}",
        f"  citation of the expected document  "
        f"{pct(sum(r.citation_correct for r in answered), len(answered))} of answered",
    ]
    if out_of_scope:
        routed = sum(not r.answered for r in out_of_scope)
        lines.append(f"  out-of-scope routed to a ticket    {pct(routed, len(out_of_scope))}")
    return lines


def miss_lines(in_scope: list[Result], out_of_scope: list[Result]) -> list[str]:
    lines = []
    for r in in_scope:
        if not r.hit(1):
            lines.append(
                f"  retrieval: {r.item.question!r} -> {r.top_docs}, want {r.item.expected}"
            )
        if not r.answered:
            lines.append(f"  ticket:    {r.item.question!r} ({r.why_ticket})")
        elif not r.citation_correct:
            lines.append(f"  citation:  {r.item.question!r} cites {r.cited_docs}")
    for r in out_of_scope:
        if r.answered:
            lines.append(f"  answered:  {r.item.question!r} (out of scope) cites {r.cited_docs}")
    return lines or ["  none"]


async def run(
    documents: list[Document],
    llm: LLMClient,
    path: Path,
    *,
    min_score: float,
    min_coverage: float,
    top_k: int,
    ablation: bool = False,
    holdout: bool = False,
) -> str:
    repo = await Repository.connect(":memory:")
    try:
        retriever = Retriever(documents, min_score=min_score, min_coverage=min_coverage)
        copilot = Copilot(retriever, llm, repo, top_k=top_k)
        in_key, out_key = (
            ("holdout", "holdout_out_of_scope") if holdout else ("questions", "out_of_scope")
        )
        in_items, out_items = load_items(path, in_key), load_items(path, out_key)

        started = time.perf_counter()
        for item in in_items:
            retriever.search(item.question, top_k)
        per_query_ms = (time.perf_counter() - started) * 1000 / max(len(in_items), 1)

        in_results = await evaluate(copilot, in_items)
        out_results = await evaluate(copilot, out_items)
        sections = sum(len(d.sections) for d in documents)
        lines = [
            f"Knowledge base: {len(documents)} documents, {sections} sections.",
            f"Set: {in_key} ({len(in_items)} questions) + {out_key} ({len(out_items)}).",
            f"Answerer: {llm.name}. Thresholds: coverage >= {min_coverage}, score >= {min_score}.",
            "",
            f"Retrieval (expected document in the top-k sections), {per_query_ms:.2f} ms/question",
            *retrieval_lines(in_results),
            "",
            "Routing and citations",
            *routing_lines(in_results, out_results),
            "",
            "Misses",
            *miss_lines(in_results, out_results),
        ]
        if ablation:
            lines += ["", f"Ablation (hit@1 / hit@3 on {in_key}, each step adds to the previous)"]
            for name, options in ABLATION_STEPS:
                variant = Retriever(documents, options)
                hits = []
                for item in in_items:
                    docs = [h.section.doc_id for h in variant.search(item.question, K).hits]
                    hits.append(docs.index(item.expected) + 1 if item.expected in docs else None)
                h1 = sum(rank == 1 for rank in hits)
                h3 = sum(rank is not None for rank in hits)
                lines.append(f"  {name:24} {h1:>2}/{len(hits)}   {h3:>2}/{len(hits)}")
        return "\n".join(lines)
    finally:
        await repo.close()
