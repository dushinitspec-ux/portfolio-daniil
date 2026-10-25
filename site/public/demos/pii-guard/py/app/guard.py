"""The masking pipeline, without any web or LLM code: detect, apply the policy, mask, check.

Gateway (gateway.py) calls Guard.prepare() before the LLM and restore() after it.
"""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Literal

from app.detectors import Detector, resolve_overlaps
from app.entities import Entity, EntityType
from app.masking import Vault, contains_value, mask
from app.policy import Action, Policy

Role = Literal["user", "assistant"]


@dataclass(frozen=True)
class Message:
    role: Role
    content: str


@dataclass(frozen=True)
class Finding:
    """How many of one entity type a request contained and what the policy did with them."""

    type: EntityType
    action: Action
    count: int  # occurrences
    distinct: int  # different values (= number of placeholders when masked)


class LeakCheckError(RuntimeError):
    """A value that should be masked is still in the outgoing text. Nothing is sent."""


@dataclass
class Prepared:
    decision: Literal["masked", "passed", "blocked"]
    findings: list[Finding]
    original: list[Message]
    masked: list[Message]
    entities: list[list[Entity]]  # per message, for highlighting on the web page
    vault: Vault

    @property
    def blocked(self) -> bool:
        return self.decision == "blocked"

    def counts(self) -> dict[str, dict[str, int | str]]:
        """Types, counts and actions only: safe for the audit log and the API."""
        return {
            f.type.value: {"count": f.count, "distinct": f.distinct, "action": f.action.value}
            for f in self.findings
        }


def _propagate(text: str, found: list[Entity], masked: dict[str, Entity]) -> list[Entity]:
    """Also mask other occurrences of values masked anywhere in the request.

    A date of birth is only recognised next to a word like "born"; if the same date
    appears again further down, it must not slip through just because the word is missing.
    """
    extra: list[Entity] = []
    for value, model in masked.items():
        start = 0
        while (index := text.find(value, start)) != -1:
            end = index + len(value)
            start = end
            candidate = replace(model, start=index, end=end)
            if any(candidate.overlaps(e) for e in [*found, *extra]):
                continue
            if contains_value(text[max(0, index - 1) : end + 1], value):
                extra.append(candidate)
    return resolve_overlaps([*found, *extra]) if extra else found


class Guard:
    def __init__(self, detector: Detector, policy: Policy) -> None:
        self.detector = detector
        self.policy = policy

    def prepare(self, messages: Sequence[Message]) -> Prepared:
        texts = [m.content for m in messages]
        entities = [self.detector.detect(t) for t in texts]

        masked_values = {
            e.value: e
            for found in entities
            for e in found
            if self.policy.action_for(e.type) is Action.MASK
        }
        if masked_values:
            entities = [
                _propagate(t, found, masked_values)
                for t, found in zip(texts, entities, strict=True)
            ]

        findings = self._findings(entities)
        vault = Vault(texts)
        if any(f.action is Action.BLOCK for f in findings):
            return Prepared("blocked", findings, list(messages), [], entities, vault)

        masked: list[Message] = []
        for message, found in zip(messages, entities, strict=True):
            to_mask = [e for e in found if self.policy.action_for(e.type) is Action.MASK]
            masked.append(Message(message.role, mask(message.content, to_mask, vault)))

        # Fail closed: if any value the policy says to mask is still in the outgoing text,
        # refuse the request instead of trusting that the masking above is perfect. The
        # list comes from the detector, not from the vault: the vault is filled by mask()
        # itself, so a broken mask() would leave it empty and the check would pass.
        for value in masked_values:
            if any(contains_value(m.content, value) for m in masked):
                raise LeakCheckError("a masked value is still present in the outgoing text")

        decision = "masked" if masked_values else "passed"
        return Prepared(decision, findings, list(messages), masked, entities, vault)

    def _findings(self, entities: list[list[Entity]]) -> list[Finding]:
        counts: Counter[EntityType] = Counter()
        values: dict[EntityType, set[str]] = {}
        for found in entities:
            for e in found:
                counts[e.type] += 1
                values.setdefault(e.type, set()).add(e.canonical)
        return [
            Finding(t, self.policy.action_for(t), counts[t], len(values[t]))
            for t in EntityType
            if counts[t]
        ]
