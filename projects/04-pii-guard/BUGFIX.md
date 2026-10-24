# Bugs found and fixed

Real bugs I hit while building this project, in the order I found them. Five of the six were
found by tests that check a property ("nothing that should be masked ever reaches the model")
on random or deliberately broken input, rather than by tests with hand-picked examples. The
hand-picked tests all passed the first time they ran, with these bugs still in the code.

---

## 1. Piped CLI output lost Turkish letters on Windows

**What broke.** `python -m app mask` prints the text as the model would receive it. Piped
into another program, a Turkish date of birth came out wrong:

```
Do?um tarihi: <DATE_OF_BIRTH_1>, ...      # input: "Doğum tarihi: 14.03.1985, ..."
```

**Root cause.** When stdout is a pipe, Python on Windows encodes it with the ANSI code page,
which is cp1251 on this Russian Windows. cp1251 has Cyrillic but no "ğ". Without any handling
the program crashes:

```
UnicodeEncodeError: 'charmap' codec can't encode character 'ğ' in position 2
```

My first version had prevented the crash with `errors="replace"`, which only swapped the crash
for a silent "?". For a tool whose whole point is showing exactly what leaves the machine,
that is still wrong.

**Fix.** Write UTF-8, whatever the console's code page:

```python
# before
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(errors="replace")
```

```python
# after
for stream in (sys.stdin, sys.stdout, sys.stderr):
    if isinstance(stream, io.TextIOWrapper):
        stream.reconfigure(encoding="utf-8")
```

A test now runs the CLI as a separate process with its output piped, exactly like the
failing case, and checks that the bytes are UTF-8 with the "ğ" intact.

---

## 2. IP address placeholders were never put back

**What broke.** The round-trip property test (random texts built from sample values;
`restore(mask(text))` must give the text back) failed on 18 of its first 40 texts:

```
- anna.schmidt@muster-gmbh.example 203.0.113.42 Hello, invoice check ...
+ anna.schmidt@muster-gmbh.example <IPV4_1> Hello, invoice check ...
```

**Root cause.** The pattern that finds placeholders in the answer only allowed letters and
underscores in the type name. `IPV4` has a digit, so `<IPV4_1>` was never recognised: the IP
address was masked correctly but never restored, and the user got a placeholder in the
answer. The hand-written tests used e-mails and IBANs, so they passed.

**Fix.** Build the pattern from the actual type names instead of describing what a type name
looks like:

```python
# before
PLACEHOLDER = re.compile(r"<\s*([A-Za-z]+(?:_[A-Za-z]+)*)_(\d+)\s*>")
```

```python
# after
_TYPE_NAMES = "|".join(sorted((t.value for t in EntityType), key=len, reverse=True))
PLACEHOLDER = re.compile(rf"<\s*({_TYPE_NAMES})_(\d+)\s*>", re.IGNORECASE)
```

---

## 3. A phone number next to other digits was not masked

**What broke.** With bug 2 fixed, the same test showed a real leak: in
`... check 2026-114 0151 23456789 invoice ...` the mobile number reached the masked text.
Two numbers in a row were not masked either:

```python
>>> [m.raw_string for m in PhoneNumberMatcher("Hello, 0151 23456789 0151 23456789", "DE", leniency=Leniency.VALID)]
[]
```

**Root cause.** libphonenumber's `PhoneNumberMatcher` takes the whole run of digits
(`2026-114 0151 23456789`) as one candidate. In `VALID` mode, when the run as a whole is not a
valid number, it found nothing inside it.

My first fix split the run into digit groups and took, from the left, the longest slice that
is a valid number. The test then failed again on `+49 30 12345678 0151 23456789`:
`+49 30 12345678 0151` is a valid Berlin number on its own, so the greedy split took it and
left `23456789` unmasked.

**Fix.** Check every slice of whole groups and choose the split of the whole run that covers
the most groups (dynamic programming over the groups). A slice that is only *possible*
(international, not assigned yet) scores a little less than a *valid* one:

```python
# before
for match in PhoneNumberMatcher(text, region, leniency=leniency):
    ...
    yield Entity(EntityType.PHONE, match.start, match.end, raw, e164)
```

```python
# after
for run in _PHONE_RUN.finditer(text):
    groups = _groups(run, _PHONE_GROUPS)
    for start, end, number in _best_split(groups, [valid, possible], _MAX_PHONE_GROUPS):
        ...

# in _best_split, for every slice groups[i..j] that a check at `level` accepts:
score = 4 * (j - i + 1) - 3 * level + best[j + 1][0]
```

The property test now also checks that no piece of a value with 4 or more characters
(such as `23456789`) appears in the masked text.

---

## 4. Two phone numbers in a row were read as a card number

**What broke.** In `+49 30 12345678 0151 23456789` the detector reported
`CARD '49 30 12345678 0151'`. With the default policy a card number blocks the request, so a
harmless prompt with two phone numbers was refused.

**Root cause.** The digits `4930123456780151` start with 4 (Visa), have 16 digits and happen
to pass the Luhn check, which any random number does one time in ten. The card finder also
started a candidate right after the "+".

**Fix.** Card numbers are printed in one block, in groups of four, or 4-6-5 / 4-6-4 (Amex,
Diners). Other groupings are not cards, and a run after "+" is a phone number:

```python
# before
_DIGIT_GROUPS = re.compile(r"(?<![\w-])\d+(?:[ -]\d+)*(?![\w])")
...
if 12 <= len(digits) <= 19 and card_is_valid(digits):
```

```python
# after
_DIGIT_GROUPS = re.compile(r"(?<![\w+-])\d+(?:[ -]\d+)*(?![\w])")
...
if card_is_valid(digits) and _card_grouping_ok([len(p) for p in parts]):

def _card_grouping_ok(lengths):
    if len(lengths) == 1:
        return True
    if list(lengths) in ([4, 6, 5], [4, 6, 4]):
        return True
    return all(n == 4 for n in lengths[:-1]) and 1 <= lengths[-1] <= 4
```

---

## 5. A phone number right after an IBAN disappeared

**What broke.** In `NL91 ABNA 0417 1643 00 0151 23456789` the IBAN was masked and the phone
number after it was not.

**Root cause.** All detectors ran on the original text, then overlaps were resolved by
priority. Reproduced with the phone finder of that time:

```python
>>> list(find_phones("NL91 ABNA 0417 1643 00 0151 23456789 please", ["DE"]))
['0417 1643 00 0151']
```

The last three groups of the IBAN plus the first group of the phone number form a number
that libphonenumber accepts as a valid German one. That candidate overlapped the IBAN, which
has higher priority, so it was thrown away as a whole, and the real phone number with it.

**Fix.** Run the detectors one by one in priority order, and blank out what each one claims
before the next one runs. The phone finder never sees the IBAN's digits:

```python
# before
candidates = [*find_ibans(text), *find_cards(text), ..., *find_phones(text, regions), ...]
return resolve_overlaps(candidates)
```

```python
# after
working = text
for entity_type in PRIORITY:
    found = resolve_overlaps(finders[entity_type](working))
    kept.extend(found)
    working = _blank_out(working, found)  # same length, so offsets stay valid
```

---

## 6. The fail-closed check trusted the step it was checking

**What broke.** After masking, the guard searches the outgoing text for every value that
should have been masked and refuses the request if one is still there. A test that replaces
`mask()` with a broken version (it returns the text unchanged) expected a `LeakCheckError`
and got none: the unmasked IBAN would have gone to the model.

```
Failed: DID NOT RAISE LeakCheckError
```

**Root cause.** The check took its list of values from the vault, and the vault is filled
by `mask()` itself. A broken `mask()` leaves the vault empty, so the check had nothing to
look for and passed.

**Fix.** Take the list from the detector's results, which do not depend on the masking step:

```python
# before
for value in vault.originals:
    if any(contains_value(m.content, value) for m in masked):
        raise LeakCheckError("a masked value is still present in the outgoing text")
```

```python
# after
for value in masked_values:  # from the detector, before masking
    if any(contains_value(m.content, value) for m in masked):
        raise LeakCheckError("a masked value is still present in the outgoing text")
```

**Lesson.** A safety check must not get its input from the thing it is checking. And a test
of a safety check has to break the protected step on purpose; otherwise it only shows that
the check stays quiet when everything works.
