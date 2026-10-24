from pathlib import Path

import pytest

import app.guard
from app.detectors import Detector
from app.entities import EntityType
from app.guard import Guard, LeakCheckError, Message
from app.policy import Action, Policy, PolicyError, load_policy, parse_policy
from tests.conftest import CARD, EMAIL, IBAN, ROOT, VAT

T = EntityType


def test_the_shipped_policy(policy: Policy) -> None:
    assert policy.action_for(T.CARD) is Action.BLOCK
    assert policy.action_for(T.VAT_ID) is Action.ALLOW
    assert policy.action_for(T.IBAN) is Action.MASK
    assert len(policy.summary()) == len(EntityType)


def test_unlisted_types_get_the_default() -> None:
    policy = parse_policy({"default": "block", "entities": {"email": "mask"}})
    assert policy.action_for(T.EMAIL) is Action.MASK  # names are case-insensitive
    assert policy.action_for(T.PHONE) is Action.BLOCK


def test_empty_policy_masks_everything() -> None:
    assert parse_policy(None).action_for(T.NAME) is Action.MASK


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"entities": {"PASSPORT": "mask"}}, "unknown entity type 'PASSPORT'"),
        ({"entities": {"EMAIL": "hide"}}, "unknown action 'hide'"),
        ({"defaults": "mask"}, "unknown keys: defaults"),
        (["mask"], "must be a mapping"),
    ],
)
def test_policy_errors_say_what_is_wrong(data: object, message: str) -> None:
    with pytest.raises(PolicyError, match=message):
        parse_policy(data)


def test_missing_policy_file(tmp_path: Path) -> None:
    with pytest.raises(PolicyError, match="not found"):
        load_policy(tmp_path / "nope.yaml")


def test_broken_yaml(tmp_path: Path) -> None:
    path = tmp_path / "policy.yaml"
    path.write_text("entities: [EMAIL: mask", encoding="utf-8")
    with pytest.raises(PolicyError, match="not valid YAML"):
        load_policy(path)


def test_block_refuses_the_whole_request(guard: Guard) -> None:
    prepared = guard.prepare([Message("user", f"mail {EMAIL}, card {CARD}")])
    assert prepared.blocked
    assert prepared.masked == []
    assert {f.type: f.action for f in prepared.findings} == {
        T.EMAIL: Action.MASK,
        T.CARD: Action.BLOCK,
    }


def test_allow_leaves_the_value_and_masks_the_rest(guard: Guard) -> None:
    prepared = guard.prepare([Message("user", f"VAT {VAT}, IBAN {IBAN}")])
    assert prepared.decision == "masked"
    assert prepared.masked[0].content == f"VAT {VAT}, IBAN <IBAN_1>"


def test_nothing_found_is_passed_unchanged(guard: Guard) -> None:
    prepared = guard.prepare([Message("user", "What is the capital of France?")])
    assert prepared.decision == "passed"
    assert prepared.masked[0].content == "What is the capital of France?"
    assert prepared.findings == []


def test_placeholders_are_shared_across_the_conversation(guard: Guard) -> None:
    prepared = guard.prepare(
        [
            Message("user", f"My e-mail is {EMAIL}."),
            Message("assistant", f"Noted: {EMAIL}."),
            Message("user", "Please repeat my e-mail."),
        ]
    )
    assert [m.content for m in prepared.masked] == [
        "My e-mail is <EMAIL_1>.",
        "Noted: <EMAIL_1>.",
        "Please repeat my e-mail.",
    ]
    assert prepared.counts() == {"EMAIL": {"count": 2, "distinct": 1, "action": "mask"}}


def test_a_masked_value_is_masked_everywhere_it_appears(guard: Guard) -> None:
    # The second date has no "born" next to it, but it is the same value.
    text = "Max Mustermann, born 14.03.1985. Please double-check 14.03.1985 in the HR file."
    prepared = guard.prepare([Message("user", text)])
    assert "14.03.1985" not in prepared.masked[0].content
    assert prepared.masked[0].content.count("<DATE_OF_BIRTH_1>") == 2


def test_fail_closed_if_masking_misses_a_value(
    guard: Guard, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Simulate a masking bug: the text comes back unchanged.
    monkeypatch.setattr(app.guard, "mask", lambda text, entities, vault: text)
    with pytest.raises(LeakCheckError):
        guard.prepare([Message("user", f"IBAN {IBAN}")])


def test_names_need_a_names_list() -> None:
    no_names = Guard(Detector(["DE"]), load_policy(ROOT / "policy.yaml"))
    prepared = no_names.prepare([Message("user", "Anna Schmidt called.")])
    assert prepared.decision == "passed"  # the honest limitation: no list, no names
