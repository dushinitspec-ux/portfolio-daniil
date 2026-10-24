# Bugs found and fixed

Real bugs I hit while building this project, in the order I found them.

---

## 1. The simulator raised false alarms on ordinary door openings

**What broke.** The test "a day of door openings must not alert" failed: 24 simulated hours
with no equipment failures produced 18 alert and recovery messages. Measured over 30 random
seeds with
3 door openings per hour, the demo raised **8.2 false alarms per day**. A demo that cries wolf
makes the product look broken, even though the alert rule itself was fine.

**Root cause.** The fridge model treated an open door as "the probe moves towards room
temperature (24 °C)". That is how a bare air sensor behaves, not a probe inside a fridge,
which sits among the food and sees mixed air. Each opening pushed the reading 2–3 °C up, and
the slow recovery (5-minute time constant) kept it above the limit for about 4 minutes. Two
openings close together crossed the 5-minute alert delay.

**Fix.** An open door now raises the target by a few degrees above the setpoint instead of
to room temperature, and the compressor recovers faster:

```python
# before
door_tau_s: float = 900.0
cool_tau_s: float = 300.0
...
elif self.mode is Mode.DOOR_OPEN:
    target, tau = p.ambient_c, p.door_tau_s          # 24 °C: like a bare air sensor
```

```python
# after
door_delta_c: float = 5.0   # how much warmer the probe's air gets while the door is open
door_tau_s: float = 300.0
cool_tau_s: float = 180.0
...
elif self.mode is Mode.DOOR_OPEN:
    target, tau = p.setpoint_c + p.door_delta_c, p.door_tau_s
```

False alarms fell from 8.2 to **0.13 per day** (same 30 seeds, same door rate). The remaining
ones come from several openings in a row during a rush, when the fridge really does stay warm.
I also replaced the vague test with two precise ones: a single 2-minute opening must reach
"pending" but never alert, and a busy week must give at most 2 false alarms.

**Lesson.** Test the fake data against the real rules. The simulator is part of the product
when it is what people see in a demo.

---

## 2. The app crashed on start with the example config

**What broke.** The very first run, `cp .env.example .env && uv run python -m app`, ended
with:

```
pydantic_core._pydantic_core.ValidationError: 1 validation error for Settings
alert_chat_id
  Input should be a valid integer, unable to parse string as an integer [input_value='']
```

**Root cause.** `.env.example` contains `ALERT_CHAT_ID=` with no value, so a new user fills it
in later. pydantic-settings read that as the string `""` and tried to convert it to
`int | None`. An empty string is not "no value" unless you say so.

**Fix.** One option in the settings class, plus a test that loads an `.env` with empty values:

```python
# before
model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
```

```python
# after
# env_ignore_empty: "ALERT_CHAT_ID=" in .env means "not set", not "parse '' as a number".
model_config = SettingsConfigDict(
    env_file=".env", env_file_encoding="utf-8", env_ignore_empty=True, extra="ignore"
)
```

**Lesson.** Run the project exactly the way the README tells a stranger to run it.

---

## 3. A wrong timezone name gave an unreadable crash

**What broke.** A test setting `TIMEZONE=Mars/Olympus` expected a normal validation error,
but got a raw `ZoneInfoNotFoundError` traceback from deep inside the standard library.

**Root cause.** `ZoneInfoNotFoundError` is a subclass of `KeyError`. Pydantic turns only
`ValueError` and `AssertionError` raised in a validator into a friendly validation error;
anything else escapes as is.

**Fix.**

```python
# before
def _check_timezone(cls, value: str) -> str:
    ZoneInfo(value)  # raises if the name is unknown
    return value
```

```python
# after
def _check_timezone(cls, value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError(f"unknown timezone {value!r}, use a name like Europe/Istanbul") from None
    return value
```

---

## 4. The history chart hid readings that the API had accepted

**What broke.** A test posted 20 readings and asked for the history; it got back 15.

**Root cause.** Sensor clocks drift, so the API accepts readings up to 5 minutes "in the
future". But the history query ended at the server's `now`. Readings from a sensor whose
clock runs fast were stored, yet missing from charts until the server clock caught up.

**Fix.** The history window ends at `now + MAX_CLOCK_SKEW`, the same tolerance the API uses:

```python
# before
until = self._clock()
points = await self._repo.readings(sensor_id, until - timedelta(hours=hours), until)
```

```python
# after
now = self._clock()
points = await self._repo.readings(sensor_id, now - timedelta(hours=hours), now + MAX_CLOCK_SKEW)
```

**Lesson.** When two parts of a system use a tolerance, they must use the same constant.
