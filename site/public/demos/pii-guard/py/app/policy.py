"""policy.yaml: what to do with each kind of personal data."""

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

import yaml

from app.entities import EntityType


class Action(StrEnum):
    MASK = "mask"  # replace with a placeholder, restore in the answer
    BLOCK = "block"  # refuse the whole request; nothing is sent to the LLM
    ALLOW = "allow"  # send as it is


class PolicyError(ValueError):
    """policy.yaml is missing, malformed or names an unknown type or action."""


@dataclass(frozen=True)
class Policy:
    default: Action = Action.MASK
    rules: dict[EntityType, Action] = field(default_factory=dict)

    def action_for(self, entity_type: EntityType) -> Action:
        return self.rules.get(entity_type, self.default)

    def summary(self) -> list[tuple[EntityType, Action]]:
        return [(t, self.action_for(t)) for t in EntityType]


def _action(value: object, where: str) -> Action:
    try:
        return Action(str(value).strip().lower())
    except ValueError:
        choices = ", ".join(a.value for a in Action)
        raise PolicyError(f"{where}: unknown action {value!r}, use one of: {choices}") from None


def parse_policy(data: object) -> Policy:
    if data is None:
        return Policy()
    if not isinstance(data, dict):
        raise PolicyError("the policy must be a mapping with 'default' and 'entities'")
    unknown_keys = set(data) - {"default", "entities"}
    if unknown_keys:
        raise PolicyError(f"unknown keys: {', '.join(sorted(map(str, unknown_keys)))}")
    default = _action(data.get("default", "mask"), "default")
    entities = data.get("entities") or {}
    if not isinstance(entities, dict):
        raise PolicyError("'entities' must map an entity type to an action")
    rules: dict[EntityType, Action] = {}
    for name, value in entities.items():
        try:
            entity_type = EntityType(str(name).strip().upper())
        except ValueError:
            known = ", ".join(t.value for t in EntityType)
            raise PolicyError(f"unknown entity type {name!r}, known types: {known}") from None
        rules[entity_type] = _action(value, str(name))
    return Policy(default, rules)


def load_policy(path: Path) -> Policy:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise PolicyError(f"policy file not found: {path}") from None
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise PolicyError(f"{path}: not valid YAML ({exc})") from None
    return parse_policy(data)
