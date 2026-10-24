"""robots.txt parsing and matching per RFC 9309.

Python's urllib.robotparser is not used: it applies the first matching rule instead of the
longest one, and it does not understand the `*` and `$` wildcards, which many shop
platforms use (`Disallow: /*?sort=`).
"""

import contextlib
import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit


@dataclass(frozen=True)
class RobotsRule:
    allow: bool
    pattern: str

    def matches(self, path: str) -> bool:
        return _compile(self.pattern).match(path) is not None


@dataclass
class _Group:
    agents: list[str] = field(default_factory=list)
    rules: list[RobotsRule] = field(default_factory=list)
    crawl_delay: float | None = None


_PATTERN_CACHE: dict[str, re.Pattern[str]] = {}


def _compile(pattern: str) -> re.Pattern[str]:
    if pattern not in _PATTERN_CACHE:
        anchored = pattern.endswith("$")
        body = pattern[:-1] if anchored else pattern
        regex = ".*".join(re.escape(part) for part in body.split("*"))
        _PATTERN_CACHE[pattern] = re.compile(regex + ("$" if anchored else ""))
    return _PATTERN_CACHE[pattern]


@dataclass
class Robots:
    """Rules for one origin. `status` says how they were obtained, for the report."""

    groups: list[_Group] = field(default_factory=list)
    status: str = "parsed"
    disallow_everything: bool = False

    @classmethod
    def allow_all(cls, status: str) -> "Robots":
        return cls(status=status)

    @classmethod
    def disallow_all(cls, status: str) -> "Robots":
        return cls(status=status, disallow_everything=True)

    @classmethod
    def parse(cls, text: str) -> "Robots":
        groups: list[_Group] = []
        current: _Group | None = None
        last_was_agent = False
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            key, value = (part.strip() for part in line.split(":", 1))
            key = key.lower()
            if key == "user-agent":
                # Consecutive user-agent lines share one group of rules.
                if current is None or not last_was_agent:
                    current = _Group()
                    groups.append(current)
                current.agents.append(value.lower())
                last_was_agent = True
                continue
            last_was_agent = False
            if current is None:
                continue  # rules before any user-agent line belong to no group
            if key in ("allow", "disallow") and value:
                current.rules.append(RobotsRule(key == "allow", value))
            elif key == "crawl-delay":
                with contextlib.suppress(ValueError):
                    current.crawl_delay = float(value)
        return cls(groups=groups)

    def _groups_for(self, product_token: str) -> list[_Group]:
        token = product_token.lower()
        own = [g for g in self.groups if token in g.agents]
        return own or [g for g in self.groups if "*" in g.agents]

    def allowed(self, url: str, product_token: str) -> bool:
        if self.disallow_everything:
            return False
        parts = urlsplit(url)
        path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        if path == "/robots.txt":
            return True
        best: RobotsRule | None = None
        for group in self._groups_for(product_token):
            for rule in group.rules:
                if not rule.matches(path):
                    continue
                # The longest pattern wins; on a tie, allow wins (RFC 9309, 2.2.2).
                if (
                    best is None
                    or len(rule.pattern) > len(best.pattern)
                    or (len(rule.pattern) == len(best.pattern) and rule.allow)
                ):
                    best = rule
        return best is None or best.allow

    def crawl_delay(self, product_token: str) -> float | None:
        delays = [g.crawl_delay for g in self._groups_for(product_token) if g.crawl_delay]
        return max(delays) if delays else None
