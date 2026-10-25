"""Loads the IT knowledge base: one Markdown file per topic, split into sections.

Format of a file:

    # Title of the document
    Optional intro paragraph (becomes the "Overview" section).
    ## Section heading
    Section text ...

A section is the unit of retrieval: small enough to be specific, big enough to carry a
complete how-to. Deeper headings (###) stay inside their section.
"""

import re
from dataclasses import dataclass
from pathlib import Path

OVERVIEW = "Overview"
SKIPPED_FILES = {"readme.md"}

_SLUG = re.compile(r"[^a-z0-9]+")


class KnowledgeBaseError(Exception):
    """The knowledge base folder or a file in it cannot be used."""


@dataclass(frozen=True)
class Section:
    doc_id: str
    doc_title: str
    heading: str
    text: str

    @property
    def id(self) -> str:
        return f"{self.doc_id}#{slugify(self.heading)}"

    @property
    def label(self) -> str:
        """What a user sees as the source: "VPN for remote work › VPN does not connect"."""
        if self.heading == OVERVIEW:
            return self.doc_title
        return f"{self.doc_title} › {self.heading}"


@dataclass(frozen=True)
class Document:
    id: str
    title: str
    sections: tuple[Section, ...]


def slugify(text: str) -> str:
    return _SLUG.sub("-", text.lower()).strip("-")


def parse_document(doc_id: str, markdown: str) -> Document:
    title: str | None = None
    heading = OVERVIEW
    lines: list[str] = []
    sections: list[Section] = []

    def flush() -> None:
        text = "\n".join(lines).strip()
        if text and title is not None:
            sections.append(Section(doc_id, title, heading, text))
        lines.clear()

    for line in markdown.splitlines():
        if line.startswith("# ") and title is None:
            title = line[2:].strip()
        elif line.startswith("## "):
            flush()
            heading = line[3:].strip()
        elif title is not None:
            lines.append(line.rstrip())
    flush()

    if title is None:
        raise KnowledgeBaseError(f"{doc_id}.md has no '# Title' line")
    if not sections:
        raise KnowledgeBaseError(f"{doc_id}.md has a title but no text")
    return Document(doc_id, title, tuple(sections))


def load_documents(directory: Path) -> list[Document]:
    if not directory.is_dir():
        raise KnowledgeBaseError(f"knowledge folder not found: {directory}")
    documents = [
        parse_document(path.stem, path.read_text(encoding="utf-8"))
        for path in sorted(directory.glob("*.md"))
        if path.name.lower() not in SKIPPED_FILES
    ]
    if not documents:
        raise KnowledgeBaseError(f"no .md files in {directory}")
    return documents
