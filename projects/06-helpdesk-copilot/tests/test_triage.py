import pytest

from app.triage import (
    Category,
    Priority,
    Triage,
    Urgency,
    apply_floor,
    is_action_request,
    summarize,
    triage_by_rules,
    urgency,
)


@pytest.mark.parametrize(
    "text",
    [
        "I clicked a link in a fake DHL email and typed my password",
        "Got a phishing mail from 'Microsoft', what now?",
        "Мне пришло подозрительное письмо, похоже на фишинг",
        "Verdächtige E-Mail mit Rechnung im Anhang",
        "My laptop was stolen at the airport",
    ],
)
def test_security_incidents_are_p1(text: str) -> None:
    t = triage_by_rules(text)
    assert (t.priority, t.category) == (Priority.P1, Category.SECURITY)
    assert urgency(text) is Urgency.SECURITY


def test_whole_office_offline_is_p1_network() -> None:
    t = triage_by_rules("The whole office has no internet since 10 minutes!")
    assert (t.priority, t.category) == (Priority.P1, Category.NETWORK)
    assert t.reason == Urgency.OUTAGE.value


def test_intern_does_not_match_internet() -> None:
    # Regression (BUGFIX.md, bug 2): the access keyword "intern" matched "internet".
    assert triage_by_rules("No internet on my laptop").category is Category.NETWORK
    assert triage_by_rules("Account for our new intern").category is Category.ACCESS


@pytest.mark.parametrize(
    ("text", "priority", "category"),
    [
        ("I'm locked out of my account", Priority.P2, Category.ACCESS),
        ("My laptop won't turn on", Priority.P2, Category.HARDWARE),
        ("The printer on floor 1 is jammed again", Priority.P3, Category.HARDWARE),
        ("Outlook is very slow today", Priority.P3, Category.EMAIL),
        ("Can I get Zoom installed?", Priority.P4, Category.SOFTWARE),
        ("Wie lautet das WLAN-Passwort für Gäste?", Priority.P4, Category.NETWORK),
    ],
)
def test_priority_and_category_rules(text: str, priority: Priority, category: Category) -> None:
    t = triage_by_rules(text)
    assert (t.priority, t.category) == (priority, category)
    assert t.by == "rules"


def test_unknown_topic_gets_default_category_and_says_so() -> None:
    t = triage_by_rules("Wann ist die Weihnachtsfeier?")
    assert t.category is Category.HARDWARE
    assert "default category" in t.reason


@pytest.mark.parametrize(
    "text",
    [
        "Can you order a new office chair for me?",
        "Please give Anna access to the Finance folder",
        "Could you please reset my MFA?",
        "Können Sie mir einen Monitor bestellen?",
        "Можете выдать доступ к папке Finance?",
        "Lütfen bana Photoshop yükleyin",
    ],
)
def test_action_requests(text: str) -> None:
    assert is_action_request(text)


@pytest.mark.parametrize(
    "text",
    ["How can I install Zoom?", "Can you tell me where the toner is?", "I need a new password"],
)
def test_questions_are_not_action_requests(text: str) -> None:
    assert not is_action_request(text)


def test_summary_is_one_short_line() -> None:
    assert summarize("my vpn is down.  Also the printer!") == "My vpn is down"
    long = "word " * 40
    summary = summarize(long)
    assert len(summary) <= 90
    assert summary.endswith("…")
    assert "\n" not in summarize("line one\nline two")


def test_llm_cannot_lower_a_rule_p1() -> None:
    rules = triage_by_rules("I clicked a phishing link")
    llm = Triage(Category.EMAIL, Priority.P3, "Suspicious link clicked", "user unsure", by="llm")
    final = apply_floor(llm, rules)
    assert final.priority is Priority.P1
    assert final.category is Category.SECURITY
    assert final.summary == "Suspicious link clicked"  # the LLM's summary is kept
    assert final.by == "llm+rules"


def test_llm_may_raise_a_priority() -> None:
    rules = triage_by_rules("Printer is slow")
    llm = Triage(Category.HARDWARE, Priority.P2, "Printer down for the team", "x", by="llm")
    assert apply_floor(llm, rules) == llm
