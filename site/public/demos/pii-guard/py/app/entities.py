"""The kinds of personal data the gateway knows, and one occurrence found in a text."""

from dataclasses import dataclass, field
from enum import StrEnum


class EntityType(StrEnum):
    EMAIL = "EMAIL"
    PHONE = "PHONE"
    IBAN = "IBAN"
    CARD = "CARD"
    VAT_ID = "VAT_ID"
    IPV4 = "IPV4"
    DATE_OF_BIRTH = "DATE_OF_BIRTH"
    NAME = "NAME"


# When two detectors claim overlapping text, the one listed first wins. Checksum-validated
# types come first: the digits of an IBAN can also look like a phone number, never the
# other way round.
PRIORITY: tuple[EntityType, ...] = (
    EntityType.IBAN,
    EntityType.CARD,
    EntityType.EMAIL,
    EntityType.VAT_ID,
    EntityType.IPV4,
    EntityType.DATE_OF_BIRTH,
    EntityType.PHONE,
    EntityType.NAME,
)


@dataclass(frozen=True)
class Entity:
    """One piece of personal data in a text.

    The value is excluded from repr(), so an entity that ends up in a log line or an
    exception message shows its type and position, never the personal data itself.
    """

    type: EntityType
    start: int
    end: int
    value: str = field(repr=False)  # exactly as written in the text
    canonical: str = field(repr=False)  # normalised: the same value gets the same placeholder

    def overlaps(self, other: "Entity") -> bool:
        return self.start < other.end and other.start < self.end
