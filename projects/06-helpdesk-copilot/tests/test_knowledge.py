from pathlib import Path

import pytest

from app.knowledge import OVERVIEW, Document, KnowledgeBaseError, load_documents, parse_document

SAMPLE = """\
# VPN for remote work

Intro text.

## Connect from home

Open WireGuard.

### Details stay in the section

More text.

## Empty section

## Troubleshooting

Check the internet first.
"""


def test_document_is_split_into_sections() -> None:
    doc = parse_document("vpn", SAMPLE)

    assert doc.title == "VPN for remote work"
    assert [s.heading for s in doc.sections] == [OVERVIEW, "Connect from home", "Troubleshooting"]
    assert "### Details stay in the section" in doc.sections[1].text
    assert doc.sections[1].id == "vpn#connect-from-home"
    assert doc.sections[0].label == "VPN for remote work"
    assert doc.sections[1].label == "VPN for remote work › Connect from home"


def test_document_without_title_is_rejected() -> None:
    with pytest.raises(KnowledgeBaseError, match="no '# Title'"):
        parse_document("broken", "## Section\ntext")
    with pytest.raises(KnowledgeBaseError, match="no text"):
        parse_document("empty", "# Only a title\n")


def test_missing_folder_is_reported(tmp_path: Path) -> None:
    with pytest.raises(KnowledgeBaseError, match="not found"):
        load_documents(tmp_path / "nope")
    with pytest.raises(KnowledgeBaseError, match=r"no \.md files"):
        load_documents(tmp_path)


def test_sample_knowledge_base(documents: list[Document]) -> None:
    ids = {d.id for d in documents}
    assert len(documents) >= 12
    assert "readme" not in {i.lower() for i in ids}  # README.md is not indexed
    assert {"wifi", "guest-wifi", "vpn", "printer", "password-reset", "mfa"} <= ids
    assert {"shared-mailbox", "new-laptop", "phishing", "backup-restore"} <= ids
    section_ids = [s.id for d in documents for s in d.sections]
    assert len(section_ids) == len(set(section_ids))
    assert all(len(d.sections) >= 3 for d in documents)
