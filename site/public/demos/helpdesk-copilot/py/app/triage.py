"""Ticket triage rules: category, priority (P1-P4) and a one-line summary.

These rules run in demo mode and whenever the LLM is unavailable. With an LLM they are
still used as a safety floor: if a rule says P1 (security incident, outage), the LLM cannot
lower it. The rules also decide routing before any answer is attempted: an outage or a
request for IT to do something goes straight to a ticket.

Matching is done on folded text (lowercase, no accents) at the start of words, so the
keyword "phish" matches "phishing" and "Phishing-Mail", and "sifre" matches "Şifremi".
"""

import re
from dataclasses import dataclass
from enum import StrEnum

from app.text import fold


class Category(StrEnum):
    ACCESS = "access"
    HARDWARE = "hardware"
    NETWORK = "network"
    EMAIL = "email"
    SECURITY = "security"
    SOFTWARE = "software"


class Priority(StrEnum):
    P1 = "P1"  # security incident or many people cannot work
    P2 = "P2"  # one person cannot work
    P3 = "P3"  # something is broken, there is a workaround
    P4 = "P4"  # a request or a question


class Urgency(StrEnum):
    SECURITY = "security incident"
    OUTAGE = "outage affecting many people"


@dataclass(frozen=True)
class Triage:
    category: Category
    priority: Priority
    summary: str
    reason: str  # why this priority, shown to the IT person
    by: str = "rules"  # "rules", "llm" or "llm+rules"


def keywords(phrases: str) -> re.Pattern[str]:
    """One regex for comma-separated keyword phrases, each matched at the start of a word.

    A phrase ending in "$" must match a whole word ("intern$" must not match "internet"), and
    so must words of three letters or less ("app" must not match "approval").
    """
    parts = []
    for phrase in phrases.split(","):
        folded = fold(phrase.strip())
        whole = folded.endswith("$") or len(folded) <= 3
        folded = folded.rstrip("$")
        if not folded:
            continue
        part = re.escape(folded).replace(r"\ ", r"\s+")
        parts.append(part + r"\b" if whole else part)
    return re.compile(rf"(?<!\w)(?:{'|'.join(parts)})")


CATEGORY_KEYWORDS: dict[Category, re.Pattern[str]] = {
    Category.SECURITY: keywords("""
        phish, suspicious, virus, malware, ransomware, hacked, hacker, clicked a link,
        clicked on a link, stolen, lost my laptop, lost my phone,
        verdächtig, gestohlen, подозрит, фишинг, вирус, взлом, украл, şüpheli, oltalama, çalındı
    """),
    Category.NETWORK: keywords("""
        wifi, wi-fi, wlan, wireless, internet, vpn, wireguard, network, offline,
        no connection, router, access point, dns, server,
        netzwerk, сеть, интернет, впн, вайфай, kablosuz
    """),
    Category.ACCESS: keywords("""
        password, locked, lock out, log in, login, sign in, sign-in, account, mfa,
        authenticator, 2fa, access to, permission, new employee, new colleague, leaving,
        contractor, intern$, passwort, konto, zugriff, пароль, учетн, аккаунт, доступ,
        şifre, parola, hesap, erişim
    """),
    Category.EMAIL: keywords("""
        email, e-mail, mail, outlook, mailbox, inbox, junk, spam, automatic repl,
        out of office, signature, calendar, shared mailbox, postfach, почт, письм, e-posta, eposta
    """),
    Category.HARDWARE: keywords("""
        printer, print, toner, paper, scan, laptop, notebook, monitor, screen, dock, keyboard,
        mouse, battery, headset, camera, projector, beamer, phone, chair, desk, machine, badge,
        drucker, bildschirm, akku, kamera, handy, telefon, принтер, ноутбук, монитор, экран,
        батаре, камер, телефон, yazıcı, dizüstü, ekran
    """),
    Category.SOFTWARE: keywords("""
        install, software, program, app, teams, zoom, excel, word, onedrive, sharepoint,
        update, license, licence, crash, error, website,
        programm, установ, программ, приложени, uygulama, yükle
    """),
}

# Tie-break order: when two categories match equally, the earlier one wins
# ("WLAN password for guests" is a network question rather than an access problem).
CATEGORY_ORDER = list(CATEGORY_KEYWORDS)
DEFAULT_CATEGORY = Category.HARDWARE

URGENT_RULES: dict[Urgency, re.Pattern[str]] = {
    Urgency.SECURITY: keywords("""
        phish, clicked a link, clicked on a link, clicked the link, entered my password,
        typed my password, virus, malware, ransomware, hacked, encrypted my files, stolen,
        lost my laptop, lost my phone, lost my company, wasn't logging in, was not logging in,
        didn't start, did not start, suspicious email, suspicious login,
        verdächtig, gestohlen, фишинг, вирус, взлом, украли, потерял ноутбук, потерял телефон,
        подозрительное письмо, şüpheli, oltalama, çalındı, kaybettim
    """),
    Urgency.OUTAGE: keywords("""
        whole office, entire office, the office has no, everyone, everybody, nobody can,
        no one can, all users, all of us, all computers, server is down, server down,
        ganze büro, alle kollegen, niemand kann, весь офис, у всех, никто не может,
        tüm ofis, herkes, kimse
    """),
}

BLOCKED = keywords("""
    can't log in, cannot log in, can't sign in, cannot sign in, can't login, locked out,
    account is locked, account locked, won't start, will not start, doesn't start,
    does not start, won't turn on, doesn't turn on, does not turn on, no internet, can't work,
    cannot work, blue screen, urgent, asap, deadline, can't send, cannot send,
    dringend, kann nicht arbeiten, срочно, не могу войти, не могу работать,
    acil, giriş yapamıyorum
""")

PROBLEM = keywords("""
    not working, doesn't work, does not work, don't work, isn't working, broken, error, stuck,
    paper jam, jammed, slow, fail, crash, leak, flicker, stripes, black, missing, disappeared,
    keeps, dropping, no signal, beeping, swollen, freez, hangs, not responding, can't, cannot,
    won't,
    funktioniert nicht, geht nicht, hängt, kaputt, не работает, сломал, ошибк,
    çalışmıyor, bozuk, hata
""")

QUESTION = keywords("""
    how, where, what, when, which, can i, could i, is it possible, request, would like, i need,
    need a, wie, wo, wann, как, где, что, nasıl, nerede
""")

# The employee asks IT to do something. The copilot cannot do it, so this becomes a ticket.
_VERBS = (
    "order|buy|give|grant|create|add|set up|install|unlock|reset|replace|repair|fix|change"
    "|book|enable|disable|remove|delete|restore|send me|get me"
)
_ACTION_PATTERNS = [
    rf"(?<!\w)(?:can|could|would|will) you (?:please )?(?:{_VERBS})\b",
    rf"(?<!\w)please (?:{_VERBS})\b",
    rf"^\s*(?:{_VERBS})\b.*\bfor me\b",
    r"(?<!\w)(?:können|könnten|kannst) sie\b.*\b(?:bestellen|geben|freischalten|einrichten)",
    r"(?<!\w)bitte\b.*\b(?:bestellen|freischalten|einrichten|installieren)",
    r"(?<!\w)(?:можете|можно) (?:мне )?(?:заказать|выдать|дать|установить|разблокировать)",
    r"(?<!\w)(?:прошу|пожалуйста) (?:закажите|выдайте|дайте|установите|разблокируйте)",
    r"(?<!\w)lütfen\b.*\b(?:verin|yükleyin|açın|kurun|alın)",
]
# Folded like the text they are matched against ("lütfen" -> "lutfen", "дайте" -> "даите").
ACTION_REQUEST = re.compile("|".join(fold(p).replace(" ", r"\s+") for p in _ACTION_PATTERNS))

SUMMARY_LENGTH = 90


def urgency(text: str) -> Urgency | None:
    folded = fold(text)
    for kind, pattern in URGENT_RULES.items():
        if pattern.search(folded):
            return kind
    return None


def is_action_request(text: str) -> bool:
    return ACTION_REQUEST.search(fold(text)) is not None


def categorize(text: str) -> tuple[Category, int]:
    """The category with the most keyword hits, and the number of hits."""
    folded = fold(text)
    counts = {c: len(p.findall(folded)) for c, p in CATEGORY_KEYWORDS.items()}
    best = max(CATEGORY_ORDER, key=lambda c: (counts[c], -CATEGORY_ORDER.index(c)))
    if counts[best] == 0:
        return DEFAULT_CATEGORY, 0
    return best, counts[best]


def prioritize(text: str) -> tuple[Priority, str]:
    folded = fold(text)
    if (kind := urgency(text)) is not None:
        return Priority.P1, kind.value
    if BLOCKED.search(folded):
        return Priority.P2, "one person cannot work"
    if PROBLEM.search(folded):
        return Priority.P3, "something is broken, a workaround may exist"
    if is_action_request(text) or QUESTION.search(folded) or "?" in text:
        return Priority.P4, "a request or a question"
    return Priority.P3, "no rule matched, default priority"


def summarize(text: str, limit: int = SUMMARY_LENGTH) -> str:
    """The first sentence, on one line, at most `limit` characters."""
    line = " ".join(text.split())
    first = re.split(r"(?<=[.!?])\s+", line, maxsplit=1)[0].rstrip(" .!")
    if len(first) > limit:
        first = first[: limit - 1].rsplit(" ", 1)[0].rstrip(",;:") + "…"
    return first[:1].upper() + first[1:]


def triage_by_rules(text: str) -> Triage:
    priority, reason = prioritize(text)
    category, hits = categorize(text)
    if urgency(text) is Urgency.SECURITY:
        category = Category.SECURITY
    elif hits == 0:
        reason += "; no category keyword, default category"
    return Triage(category, priority, summarize(text), reason, by="rules")


def apply_floor(llm: Triage, rules: Triage) -> Triage:
    """The LLM may raise a priority but never lower a rule-based P1."""
    if rules.priority is Priority.P1 and llm.priority is not Priority.P1:
        category = Category.SECURITY if rules.category is Category.SECURITY else llm.category
        return Triage(
            category,
            Priority.P1,
            llm.summary,
            f"{rules.reason} (rule kept P1, the model said {llm.priority})",
            by="llm+rules",
        )
    return llm
