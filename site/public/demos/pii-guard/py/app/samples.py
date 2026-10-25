"""Sample prompts for the web page. Every value in them is a published example or made up:
the IBAN is the widely published German example IBAN, the card is a well-known test
number, the IP address is from the documentation range (RFC 5737), the e-mail domains end
in .example (reserved by RFC 2606), the VAT ID and phone numbers are placeholders, and
Muster GmbH and the people are fictional.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Sample:
    id: str
    label: str
    text: str


SAMPLES: tuple[Sample, ...] = (
    Sample(
        "refund",
        "Refund request",
        "Write a short, polite reply to this customer.\n\n"
        "Hello, this is Anna Schmidt from Muster GmbH. Please refund invoice 2026-114 to "
        "our account DE89 3704 0044 0532 0130 00 and send the confirmation to "
        "anna.schmidt@muster-gmbh.example. You can reach me at +49 30 12345678. "
        "Our VAT ID is DE123456789.",
    ),
    Sample(
        "onboarding",
        "New colleague",
        "Draft a welcome e-mail for our new colleague Max Mustermann (geb. 14.03.1985). "
        "His mobile is 0151 23456789 and his work address will be "
        "max.mustermann@muster-gmbh.example.",
    ),
    Sample(
        "server-log",
        "Server log",
        "Explain what happened in this log in two sentences.\n\n"
        "09:12:01 login failed for erika.mustermann@muster-gmbh.example from 203.0.113.42\n"
        "09:12:07 login failed for erika.mustermann@muster-gmbh.example from 203.0.113.42\n"
        "09:12:15 account locked after 3 failed attempts",
    ),
    Sample(
        "card",
        "Card number (blocked)",
        "A customer sent this, can you check it? My card is 4111 1111 1111 1111, "
        "please charge the remaining 49 EUR.",
    ),
)

SAMPLES_BY_ID = {s.id: s for s in SAMPLES}
DEFAULT_SAMPLE = SAMPLES[0]
