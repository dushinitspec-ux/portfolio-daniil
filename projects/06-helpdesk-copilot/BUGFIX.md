# Bugs found and fixed

Real bugs I hit while building this project, in the order I found them. The first two showed
up when I read the evaluation's output line by line instead of only looking at the totals.

---

## 1. Contractions stayed in the question and lowered the confidence

**What broke.** In the first evaluation run I printed the search terms of every missed
question. For "I got an approval request on my phone but I wasn't logging in" they were:

```
('approval', 'request', 'phon', 'wasn', 'log')
```

"wasn" is not a word. It matched nothing in the knowledge base, so the retriever treated it as
an unknown word, and unknown words get the highest weight in the confidence check (that is
what makes "the coffee machine is leaking" fail). Every question with "don't", "wasn't" or
"doesn't" looked less covered than it was.

**Root cause.** The tokenizer splits on apostrophes: "wasn't" becomes "wasn" + "t". The
one-letter "t" is dropped, but the stopword list contained "wasnt", "dont", "doesnt", forms
the tokenizer never produces.

**Fix.** List the parts the tokenizer actually produces:

```python
# before
    thanks thank im dont doesnt cant wasnt isnt didnt still even
```

```python
# after
    thanks thank still even
    don doesn didn isn wasn aren weren couldn wouldn won haven hasn ll ve re
```

The confidence (coverage) of that question went from 0.36 to 0.52, and of "Outlook says
working offline and I don't get any emails" from 0.47 to 0.61. A regression test checks that
"I wasn't logging in and I don't know why" gives only `["log", "know"]`.

**Lesson.** Test a stopword list against the tokenizer's output, not against how the words
are spelled.

---

## 2. "The whole office has no internet" was filed as an access problem

**What broke.** When I ran the triage rules over the evaluation questions, the office-wide
outage came out as P1 (correct) but in the category **access**, next to password resets:

```
P1 access    | The whole office has no internet since 10 minutes!
P4 access    | We have a workshop with 15 external people next week, can they get int...
```

**Root cause.** Keywords are matched at the start of a word, so that "phish" also matches
"phishing" and "Phishing-Mail". The access keyword "intern" (accounts for interns) therefore
matched "internet" too, and access is checked before network when the counts tie.

**Fix.** A keyword can now require a whole word with a trailing `$`:

```python
# before
        folded = fold(phrase.strip())
        ...
        parts.append(part + r"\b" if len(folded) <= 3 else part)

    ... contractor, intern, passwort, ...
```

```python
# after
        folded = fold(phrase.strip())
        whole = folded.endswith("$") or len(folded) <= 3
        folded = folded.rstrip("$")
        ...
        parts.append(part + r"\b" if whole else part)

    ... contractor, intern$, passwort, ...
```

In the same change, network now wins a tie over access ("WLAN password for guests" is a
network question). Both questions are now in **network**. A test checks
"No internet on my laptop" (network) next to "Account for our new intern" (access).

---

## 3. A Turkish request with two words before the verb was not recognized

**What broke.** The test for requests that must go straight to IT failed for one example:

```
FAILED tests/test_triage.py::test_action_requests[Lütfen bana Photoshop yükleyin]
AssertionError: assert False
```

"Lütfen bana Photoshop yükleyin" means "please install Photoshop for me".

**Root cause.** Two mistakes in one pattern. `lütfen \w* ?(?:verin|yükleyin|…)` allowed at
most one word between "please" and the verb. And every pattern goes through
`.replace(" ", r"\s+")`, so that several spaces in a message still match. That replacement
also turned the optional space ` ?` into `\s+?`, which is a lazy but **required** run of
whitespace. The German "bitte …" pattern had the same problem.

**Fix.** Allow any words between the two parts:

```python
# before
    r"(?<!\w)bitte \w* ?(?:bestellen|freischalten|einrichten|installieren)",
    r"(?<!\w)lütfen \w* ?(?:verin|yükleyin|açın|kurun|alın)",
```

```python
# after
    r"(?<!\w)bitte\b.*\b(?:bestellen|freischalten|einrichten|installieren)",
    r"(?<!\w)lütfen\b.*\b(?:verin|yükleyin|açın|kurun|alın)",
```

**Lesson.** A global rewrite of a regex (here: spaces to `\s+`) changes the meaning of
whatever stands next to the rewritten character.

---

## 4. "Coverage 0.30" was shown for a question that failed the 0.30 threshold

**What broke.** While checking an example for the README, the terminal said:

```
$ uv run python -m app --demo ask "Wie verbinde ich das VPN?"
Coverage 0.30

Ticket: P4 network - Wie verbinde ich das VPN?
```

The ticket's reason read "coverage 0.30, needed 0.30", which looks like a contradiction to
the IT person reading it.

**Root cause.** The real coverage was 0.29987. The check compares the exact value
(0.29987 < 0.30, so a ticket is right), but the text used `f"{coverage:.2f}"`, which rounds
it up to "0.30".

**Fix.** Round down for display, in one place, used by the ticket reason, the Try page and
the terminal:

```python
# before
detail = f"coverage {retrieval.coverage:.2f}, needed {self.retriever.min_coverage:.2f}"
```

```python
# after
@property
def coverage_label(self) -> str:
    """Two decimals rounded down, so a failing 0.298 is never shown as "0.30"."""
    return f"{math.floor(self.coverage * 100) / 100:.2f}"


detail = f"coverage {retrieval.coverage_label}, needed {self.retriever.min_coverage:.2f}"
```

Now: "coverage 0.29, needed 0.30". (The question itself becomes a ticket because "verbinden"
is not in the German glossary; see README, "Limitations".)
