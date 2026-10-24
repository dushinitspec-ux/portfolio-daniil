"""The hotel knowledge base: a Markdown file split into topics by '## ' headings."""

from dataclasses import dataclass
from pathlib import Path


class KnowledgeBaseError(Exception):
    pass


@dataclass(frozen=True)
class Section:
    title: str
    body: str


@dataclass(frozen=True)
class KnowledgeSnapshot:
    text: str
    sections: list[Section]


def parse_sections(text: str) -> list[Section]:
    sections: list[Section] = []
    title: str | None = None
    lines: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if title is not None:
                sections.append(Section(title, "\n".join(lines).strip()))
            title, lines = line[3:].strip(), []
        elif title is not None:
            lines.append(line)
    if title is not None:
        sections.append(Section(title, "\n".join(lines).strip()))
    return sections


class KnowledgeBase:
    """Holds the current snapshot; /reload swaps it in one assignment."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._snapshot = self._read()

    def _read(self) -> KnowledgeSnapshot:
        try:
            text = self.path.read_text(encoding="utf-8")
        except OSError as exc:
            raise KnowledgeBaseError(f"cannot read {self.path}: {exc.strerror}") from exc
        sections = parse_sections(text)
        if not sections:
            raise KnowledgeBaseError(f"{self.path} has no '## ' sections")
        return KnowledgeSnapshot(text=text.strip(), sections=sections)

    def reload(self) -> KnowledgeSnapshot:
        """Re-read the file. On error the old knowledge stays in use."""
        self._snapshot = self._read()
        return self._snapshot

    @property
    def text(self) -> str:
        return self._snapshot.text

    @property
    def sections(self) -> list[Section]:
        return self._snapshot.sections
