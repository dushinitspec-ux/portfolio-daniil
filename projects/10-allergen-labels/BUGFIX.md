# Bugs found and fixed

Real bugs I hit while building this project, in the order I found them.

---

## 1. German adjectives were reported as unknown words

**What broke.** The first run of the evaluation on my labelled sample
(`uv run python -m app.evaluate`) found every expected allergen, but flagged 42 of 116 lines
for a person to check. Among the reasons:

```
[de] gehackte Walnüsse       unknown: gehackte
[de] geriebener Parmesan     unknown: geriebener
```

"gehackt" (chopped) and "gerieben" (grated) are in the dictionary of known words. Even
"frische Kräuter" (fresh herbs) was flagged. No allergen was missed, but every such flag is
work for the chef, and a tool that cries wolf gets ignored.

**Root cause.** Two problems, found one after the other.

German words of four or more letters are matched *inside* compound words ("Weizen" in
"Weizenmehl"), so their pattern has no word boundaries. I had left out the endings too, so
"gehackt" matched only the first seven letters of "gehackte". The leftover "e" made the word
partly covered by a *known* word only, and the matcher reports such words as unknown on
purpose: otherwise "Salat" would make "Waldorfsalat" look harmless.

After adding the endings, "gehackte" passed but "geriebener" still failed. The endings were
written as `(?:e|en|er|ern|n|s|es)?`. A regex alternation takes the first alternative that
lets the whole pattern match, and with no word boundary after it, "e" is always enough: the
match stopped at "geriebene" and left the "r".

**Fix.** Add the endings to compound patterns, longest ending first:

```python
# before
_DE_ENDINGS = "(?:e|en|er|ern|n|s|es)?"
...
    if compound:
        return re.escape(words[0])
```

```python
# after
# Longest first: inside a compound there is no word boundary to force backtracking, so
# "(?:e|er)" would stop at "geriebene" + "r".
_DE_ENDINGS = "(?:ern|en|er|es|e|n|s)?"
...
    if compound:
        # Inside a compound there are no word boundaries, but the word can still take an
        # ending: "gehackt" -> "gehackte", "frisch" -> "frische".
        return re.escape(words[0]) + _DE_ENDINGS
```

Flagged lines on the sample went from 42 to 40, still with 104 of 104 allergens found.
`test_german_adjective_endings_are_known_words` keeps it fixed.

**Lesson.** Measure on text written the way people write it. The unit tests used nouns
("Weizenmehl", "Eier"); the first adjective in a real ingredient line showed the gap.

---

## 2. The app did not start: `'function' object is not subscriptable`

**What broke.** The first `uv run pytest` stopped before running a single test:

```
tests\conftest.py:9: in <module>
    from app.service import Kitchen
app\service.py:163: in Kitchen
    async def history(self, dish_id: int) -> tuple[list[Confirmation], list[Event]]:
E   TypeError: 'function' object is not subscriptable
```

**Root cause.** The `Kitchen` class had a method called `list` (the list of dishes), defined
above `history`. Python evaluates a method's annotations when the class body runs, and
inside a class body a name is looked up in the class namespace first. So `list[...]` in the
annotation of `history` meant "my method `list`", not the built-in type.

**Fix.** Rename the method; the built-in is no longer shadowed:

```python
# before
    async def list(self, include_archived: bool = False) -> list[DishView]:
```

```python
# after
    async def dishes(self, include_archived: bool = False) -> list[DishView]:
```

**Lesson.** Do not name methods after built-ins that the same class uses in annotations.
The ruff rule set shared by the projects in this repository does not include
flake8-builtins; I checked afterwards, and `ruff check --select A` reports exactly this
case as A003.

---

## 3. The menu legend cut words in half

**What broke.** The legend under the printed menu shows a short label and the official
wording, e.g. "8 **Nuts** — almonds, hazelnuts, …". To avoid "Nuts — Nuts: almonds", I
removed the label from the start of the wording. When I printed the legend for all four
languages before taking the screenshots, German and Turkish came out wrong:

```
de  1 Gluten — haltiges Getreide: Weizen …
de  4 Fisch  — e
tr  1 Gluten — içeren tahıllar: buğday …
```

**Root cause.** `startswith` compares letters, not words. "Glutenhaltiges" starts with
"Gluten" and "Fische" with "Fisch". My second attempt (strip only when the next character is
not a letter) fixed German, but turned the Turkish "Gluten içeren tahıllar" (cereals
containing gluten) into "içeren tahıllar", which means nothing on its own.

**Fix.** Strip the label only when the wording continues with ":" or " (", which is how the
regulation writes "Nuts: almonds…" and "Milk (including lactose)":

```python
# before
        if self.name.startswith(self.label):
            return self.name[len(self.label) :].lstrip(": ")
        return self.name
```

```python
# after
        rest = self.name[len(self.label) :]
        # Only "Label: ..." or "Label (...)": "Glutenhaltiges Getreide" and "Gluten içeren
        # tahıllar" must stay whole.
        if self.name.startswith(self.label) and (not rest or rest.startswith((":", " ("))):
            return rest.lstrip(": ")
        return self.name
```

The menu test now checks the German legend for "Schalenfrüchte", "Glutenhaltiges Getreide"
and "Eier".

**Lesson.** A rule that is right for English text is not automatically right for German
compounds or Turkish word order. Look at the output in every language before calling it
done.

---

## 4. A line of short words passed as "none of the 14"

**What broke.** In the final check I sent `tahini, Worcestershire sauce, fıstık` to
`/api/check` with curl from Git Bash. The answer had no peanuts or pistachios and no
warning. Curl had sent `f?st?k`: on this Windows the command line goes through the ANSI code
page (cp1251), which has no Turkish "ı". The garbling was the shell's fault, but the answer
was mine, and the same happened to a real ingredient, "XO" (XO sauce, made with dried
shrimp and scallops):

```
'f?st?k'  none  [] []
'XO'      none  [] []
```

**Root cause.** The unknown-word check skips words shorter than three letters, so that
filler like "of", "g" or "и" is not reported. "f?st?k" splits into "f", "st" and "k"; "XO"
has two letters. Nothing matched, nothing was reported, and the status fell through to
"none": the one answer this tool must never give without a reason.

**Fix.** A line in which nothing at all was recognised is reported as unknown as a whole,
and a word with a question mark inside is flagged with a note about the encoding:

```python
# before
        if partly_strong or len(m.group()) < 3:
            continue
        unknown.append(as_written(m.start(), m.end()))
```

```python
# after
        if partly_strong or len(m.group()) < 3:
            continue
        unknown.append(as_written(m.start(), m.end()))
    # Words under three letters are skipped as filler ("of", "g", "и"), but a line in which
    # nothing at all was recognised must not pass as "none of the 14": "XO" (sauce with
    # dried shrimp and scallops), or text garbled to "f?st?k" by a wrong encoding.
    if not covered and not unknown and WORD_RE.search(folded):
        unknown.append(nfc.strip())
    for token in re.findall(r"[^\s,;]+", nfc):
        if ("?" in token or "�" in token) and any(ch.isalpha() for ch in token):
            if token not in unknown:
                unknown.append(token)
            notes.append(GARBLED_NOTE)
```

The same request from a UTF-8 client returns 1, 4, 5, 8 and 11 with `fıstık` flagged, as it
should. Four regression tests cover "XO", garbled text and a garbled word next to a known
one; the labelled sample is unchanged (104 of 104, 40 lines flagged).

**Lesson.** In a safety tool the default must be "a person looks". Every path that ends in
"nothing found" needs a positive reason to get there, not just the absence of a match.
