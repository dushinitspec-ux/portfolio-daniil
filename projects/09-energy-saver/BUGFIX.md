# Bugs found and fixed

Real bugs I hit while building this project, in the order I found them. The first two only
showed up because the demo runs on real prices: 25 October 2026 was a windy Sunday, and the
German day-ahead price sat at 0.00 or -0.01 EUR/MWh from 02:00 to 16:00.

---

## 1. "-0.00 €" on a day with negative prices

**What broke.** The first demo run printed tomorrow's plan like this:

```
Hot-water boiler · 6 kW · 3 h
  02:15 CEST–02:00 CET, 02:15 CET–03:45, 04:00–04:45
  -0.00 € instead of 0.29 € (−0.29 €)
...
Expected cost -0.00 € instead of 3.41 € if every device started when its window opens.
```

and the web page showed the day's lowest price as `-0.0` ct/kWh.

**Root cause.** The planner did the right thing: it chose the slots at -0.01 EUR/MWh, so
the boiler would have been paid 0.00003 € to run. Costs are `Decimal`, and
`Decimal.quantize` keeps the sign of a value that rounds to zero:

```python
>>> Decimal("-0.00003").quantize(Decimal("0.01"))
Decimal('-0.00')
```

Floats do the same (`f"{-0.00003:.2f}"` is `'-0.00'`), so switching types would not help.

**Fix.** One rounding helper for money and one for ct/kWh; a result that rounds to zero
loses its sign. Real negative amounts (a plan that earns money on strongly negative
prices) still print with a minus.

```python
# before
def money(value: Decimal | None) -> str:
    if value is None:
        return "—"
    return f"{value.quantize(CENT, ROUND_HALF_UP):.2f} €"
```

```python
# after
def cents(value: Decimal) -> Decimal:
    """Round to cents; -0.004 becomes 0.00, not "-0.00"."""
    rounded = value.quantize(CENT, ROUND_HALF_UP)
    return abs(rounded) if rounded == 0 else rounded


def money(value: Decimal | None) -> str:
    return "—" if value is None else f"{cents(value):.2f} €"
```

The test feeds it `-0.00015`, the real cost of one of those slots, and expects `0.00 €`.

---

## 2. The day's price range included the evening before

**What broke.** The page header says "Spot price 7.0–28.7, ct/kWh over 24 h of the day".
When I compared the label with the code, the numbers came from every price in the chart,
and the chart starts at 18:00 the day before, because the EV charger's window
(18:00–08:00) belongs to the day it ends on. On 22 October both ranges happened to be equal,
so the screenshot looked right. For Sunday 25 October the old code gives `-0.0–11.1`, but
Sunday never went above 7.2 ct/kWh: 11.1 was Saturday at 19:00.

**Root cause.** `DayPlan.slots` is the whole planning horizon (Saturday 18:00 to Sunday
24:00), not the calendar day. I used the convenient list instead of the one the label
promised.

**Fix.** Filter to the local day first, and say so in the label:

```python
# before
def price_stats(plan: DayPlan) -> tuple[str, str]:
    if not plan.slots:
        return "—", "—"
    low = min(plan.slots, key=lambda s: s.price)
    high = max(plan.slots, key=lambda s: s.price)
```

```python
# after
def price_stats(plan: DayPlan) -> tuple[str, str]:
    """Lowest and highest price of the day itself (not of the evening before)."""
    start, end = day_bounds(plan.day, plan.tz)
    day_slots = [s for s in plan.slots if start <= s.start < end]
    if not day_slots:
        return "—", "—"
    low = min(day_slots, key=lambda s: s.price)
    high = max(day_slots, key=lambda s: s.price)
```

The web test now opens 25 October and expects `0.0–7.2`.

---

## 3. The demo prices would never have reached the repository

**What broke.** Before handing the project over I checked what git would actually commit:

```
$ git check-ignore -v projects/09-energy-saver/data/fixtures/energy-charts-de-lu.json
.gitignore:17:data/	projects/09-energy-saver/data/fixtures/energy-charts-de-lu.json
```

Everything worked on my machine, but on a fresh clone (or in a Docker build from the
repository) the demo, the backtest and the web tests would all fail with
`FileNotFoundError`.

**Root cause.** The repository's `.gitignore` drops every `data/` folder, because that is
where the projects keep their SQLite databases. I had put the bundled prices next to the
database.

**Fix.** Runtime data and bundled data live apart: the price file moved to `fixtures/`, and
`data/` holds only the cache, which also lets Docker mount a volume on `/app/data` without
hiding the demo prices.

```python
# before
DEFAULT_FIXTURE = Path(__file__).parent.parent / "data" / "fixtures" / "energy-charts-de-lu.json"
```

```python
# after
DEFAULT_FIXTURE = Path(__file__).parent.parent / "fixtures" / "energy-charts-de-lu.json"
```

A test checks that the file exists and is not inside a `data/` folder.

**Lesson.** "It works on my machine" includes files that git will never see. Check
`git status --untracked-files=all` before calling a project done.
