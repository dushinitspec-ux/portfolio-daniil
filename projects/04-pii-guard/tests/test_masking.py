import random

from app.detectors import Detector
from app.entities import Entity, EntityType
from app.guard import Guard, Message
from app.llm.demo import DemoLLM
from app.masking import Vault, mask, restore, unknown_placeholders
from tests.conftest import CARD, EMAIL, IBAN, IP, PHONE

T = EntityType


def masked(detector: Detector, text: str) -> tuple[str, Vault]:
    vault = Vault([text])
    return mask(text, detector.detect(text), vault), vault


def test_same_value_same_placeholder_numbered_per_type(detector: Detector) -> None:
    text = f"{EMAIL}, then max@muster.example, then {EMAIL} again"
    out, _ = masked(detector, text)
    assert out == "<EMAIL_1>, then <EMAIL_2>, then <EMAIL_1> again"


def test_print_and_electronic_iban_are_the_same_value(detector: Detector) -> None:
    out, vault = masked(detector, f"{IBAN} = DE89370400440532013000")
    assert out == "<IBAN_1> = <IBAN_1>"
    assert restore("Pay to <IBAN_1>.", vault) == f"Pay to {IBAN}."  # first spelling wins


def test_restore_every_repetition_of_a_placeholder(detector: Detector) -> None:
    _, vault = masked(detector, f"mail {EMAIL}")
    answer = "<EMAIL_1>! Yes, <EMAIL_1>. I repeat: <EMAIL_1>"
    assert restore(answer, vault) == f"{EMAIL}! Yes, {EMAIL}. I repeat: {EMAIL}"


def test_restore_tolerates_the_spellings_models_produce(detector: Detector) -> None:
    _, vault = masked(detector, f"mail {EMAIL}")
    assert restore("<email_1> and < EMAIL_1 >", vault) == f"{EMAIL} and {EMAIL}"


def test_invented_placeholders_stay_as_they_are(detector: Detector) -> None:
    _, vault = masked(detector, f"mail {EMAIL}")
    answer = "Sent to <EMAIL_1> and <EMAIL_7>."
    assert restore(answer, vault) == f"Sent to {EMAIL} and <EMAIL_7>."
    assert unknown_placeholders(answer, vault) == ["<EMAIL_7>"]


def test_placeholders_already_in_the_text_are_not_reused(detector: Detector) -> None:
    text = f"Template says <EMAIL_1>, the real one is {EMAIL}"
    out, vault = masked(detector, text)
    assert out == "Template says <EMAIL_1>, the real one is <EMAIL_2>"
    assert restore(out, vault) == text


def test_vault_repr_hides_values() -> None:
    vault = Vault()
    vault.placeholder_for(Entity(T.EMAIL, 0, len(EMAIL), EMAIL, EMAIL))
    assert EMAIL not in repr(vault)


# --- Round-trip property ---------------------------------------------------------------

VALUES = [
    EMAIL,
    "max.mustermann@muster-gmbh.example",
    IBAN,
    "NL91 ABNA 0417 1643 00",
    PHONE,
    "0151 23456789",
    "+44 7700 900123",
    CARD,
    IP,
    "Anna Schmidt",
    "Max Mustermann",
]
# Filler includes stray numbers, so values end up right next to other digits.
FILLER = ["Hello,", "please", "check", "the", "invoice", "2026-114", "today.", "and", "12", "3"]
RUNS = 500


def test_round_trip_property(detector: Detector) -> None:
    """On random texts: no masked value (or any 4+ character piece of one) reaches the
    model, every distinct value gets one placeholder, and restore(mask(x)) == x."""
    for seed in range(RUNS):
        rng = random.Random(seed)
        words = [
            rng.choice(VALUES if rng.random() < 0.3 else FILLER) for _ in range(rng.randint(3, 30))
        ]
        text = "".join(w + rng.choice([" ", " ", " ", ", ", "\n"]) for w in words).strip()
        present = [v for v in VALUES if v in text]

        out, vault = masked(detector, text)

        for value in present:
            assert value not in out, seed
            for piece in value.replace("@", " ").replace(".", " ").split():
                if len(piece) >= 4 and piece not in FILLER:
                    assert piece not in out, (seed, piece)
        assert restore(out, vault) == text, seed
        # Never fewer placeholders than values (two values merged into one). More is
        # possible: "+49 30 12345678 12" is itself a valid Berlin number, so a stray "12"
        # after a phone number is masked with it. Over-masking is the safe direction.
        assert len(vault) >= len(present), seed


async def test_round_trip_through_the_demo_model(guard: Guard) -> None:
    text = f"Refund to {IBAN}, confirm to {EMAIL}, call {PHONE}."
    prepared = guard.prepare([Message("user", text)])
    answer = await DemoLLM().complete("", prepared.masked)

    sent = prepared.masked[0].content
    for value in (IBAN, EMAIL, PHONE):
        assert value not in sent
        assert value not in answer  # the model never had it
        assert value in restore(answer, prepared.vault)


def test_card_numbers_never_reach_the_masked_text(guard: Guard) -> None:
    prepared = guard.prepare([Message("user", f"card {CARD}")])
    assert prepared.blocked
    assert prepared.masked == []
