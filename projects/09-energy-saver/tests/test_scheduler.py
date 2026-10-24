from datetime import UTC, date, datetime, time, timedelta

import httpx
import pytest

from app.db import PriceCache
from app.devices import ShellyPlug, SiteConfig
from app.planner import plan_day
from app.scheduler import DailyPlanSender, Switcher, preview_switching
from app.service import PlanService
from app.shelly import ShellyController, command_url, desired_states
from tests.conftest import TZ, flat_grid, grid_from, hours, make_device, site_with

MIDNIGHT = datetime(2026, 10, 21, 22, tzinfo=UTC)  # 22 Oct 2026 00:00 in Berlin
DAY = date(2026, 10, 22)


class RecordingNotifier:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def send(self, text: str) -> None:
        self.messages.append(text)


def plug(host: str = "192.0.2.10", generation: int = 2) -> dict[str, object]:
    return {"host": host, "generation": generation}


# --- Shelly ---------------------------------------------------------------------------------


def test_command_urls_for_both_generations() -> None:
    gen2 = ShellyPlug(host="192.0.2.10")
    gen1 = ShellyPlug(host="192.0.2.11", generation=1, channel=1)
    assert command_url(gen2, True, 3720) == (
        "http://192.0.2.10/rpc/Switch.Set?id=0&on=true&toggle_after=3720"
    )
    assert command_url(gen2, False) == "http://192.0.2.10/rpc/Switch.Set?id=0&on=false"
    assert command_url(gen1, True, 60) == "http://192.0.2.11/relay/1?turn=on&timer=60"
    assert command_url(gen1, False, 60) == "http://192.0.2.11/relay/1?turn=off"


async def test_dry_run_logs_once_per_change_and_sends_nothing() -> None:
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200)

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    boiler = make_device(name="Boiler", window="00:00-02:00", shelly=plug())
    grid = grid_from(MIDNIGHT, [50, 50, 10, 10, 10, 10, 50, 50])  # cheap 00:30-01:30
    plan = plan_day([boiler], grid, DAY, TZ)
    controller = ShellyController(http, [boiler], dry_run=True)

    lines = await preview_switching(plan, controller)
    assert lines == [
        "     00:30  DRY-RUN Boiler ON: GET http://192.0.2.10/rpc/Switch.Set?id=0&on=true"
        "&toggle_after=3720",
        "     01:30  DRY-RUN Boiler OFF: GET http://192.0.2.10/rpc/Switch.Set?id=0&on=false",
    ]
    assert sent == []


async def test_live_mode_calls_the_plug_and_retries_after_a_failure() -> None:
    calls: list[str] = []
    fail = [True]

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if fail[0]:
            fail[0] = False
            return httpx.Response(500)
        return httpx.Response(200, json={"was_on": False})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    pump = make_device(name="Pump", window="00:00-02:00", shelly=plug())
    plan = plan_day([pump], flat_grid(MIDNIGHT, MIDNIGHT + hours(24)), DAY, TZ)
    controller = ShellyController(http, [pump], dry_run=False)
    now = MIDNIGHT + timedelta(minutes=5)
    assert await controller.apply(desired_states([plan], now), now) == []  # HTTP 500
    actions = await controller.apply(desired_states([plan], now), now)
    assert actions == [
        "Pump ON: GET http://192.0.2.10/rpc/Switch.Set?id=0&on=true&toggle_after=3420"
    ]
    assert len(calls) == 2
    assert await controller.apply(desired_states([plan], now), now) == []  # no change


# --- Daily message --------------------------------------------------------------------------


@pytest.fixture
def boiler_site() -> SiteConfig:
    return site_with(make_device(name="Boiler", power_kw="6", run_time="1h", window="22:00-07:00"))


async def test_daily_plan_is_sent_once_after_send_at(
    cache: PriceCache, boiler_site: SiteConfig
) -> None:
    grid = flat_grid(MIDNIGHT - hours(24), MIDNIGHT + hours(24))
    await cache.save("DE-LU", grid, "test", "", MIDNIGHT)
    service = PlanService(cache, None, boiler_site, "DE-LU", TZ, lambda: MIDNIGHT)
    notifier = RecordingNotifier()
    sender = DailyPlanSender(service, notifier, time(14), time(20), "DE-LU")

    before = datetime(2026, 10, 21, 11, tzinfo=UTC)  # 13:00 in Berlin
    assert await sender.tick(before) is None
    after = datetime(2026, 10, 21, 12, 5, tzinfo=UTC)  # 14:05
    text = await sender.tick(after)
    assert text is not None and text.startswith("⚡ Plan for Thursday 22 Oct 2026")
    assert await sender.tick(after + timedelta(minutes=5)) is None  # already sent
    assert notifier.messages == [text]


async def test_late_prices_are_retried_then_reported(
    cache: PriceCache, boiler_site: SiteConfig
) -> None:
    service = PlanService(cache, None, boiler_site, "DE-LU", TZ, lambda: MIDNIGHT)
    notifier = RecordingNotifier()
    sender = DailyPlanSender(service, notifier, time(14), time(20), "DE-LU")
    assert await sender.tick(datetime(2026, 10, 21, 13, tzinfo=UTC)) is None  # 15:00, retry
    text = await sender.tick(datetime(2026, 10, 21, 18, tzinfo=UTC))  # 20:00
    assert text is not None and "still not published" in text
    assert len(notifier.messages) == 1


async def test_switcher_falls_back_to_window_start_without_prices(cache: PriceCache) -> None:
    boiler = make_device(name="Boiler", run_time="2h", window="22:00-07:00", shelly=plug())
    service = PlanService(cache, None, site_with(boiler), "DE-LU", TZ, lambda: MIDNIGHT)
    controller = ShellyController(httpx.AsyncClient(), [boiler], dry_run=True)
    switcher = Switcher(service, controller)
    at_22 = MIDNIGHT - hours(2)  # 21 Oct 22:00, no prices at all in the cache
    actions = await switcher.tick(at_22)
    assert actions and "Boiler ON" in actions[0]
