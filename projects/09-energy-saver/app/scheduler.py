"""Background jobs: the daily "tomorrow's plan" message and switching the Shelly plugs.

Each job is a `tick(now)` that does one round and is easy to test with a fixed clock;
`run_forever` only calls it in a loop. A failure in one round is logged and the loop goes on.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, time, timedelta

from app.messages import clock, format_not_published, format_plan
from app.notifier import Notifier
from app.planner import DayPlan, fallback_plan, slot_starts
from app.service import PlanService
from app.shelly import ShellyController, desired_states

logger = logging.getLogger("energy.scheduler")


class DailyPlanSender:
    """At `send_at` local time, send tomorrow's plan once. If the prices are not out yet,
    try again on every tick until `retry_until`, then send a warning instead."""

    def __init__(
        self,
        service: PlanService,
        notifier: Notifier,
        send_at: time,
        retry_until: time,
        bidding_zone: str,
    ) -> None:
        self.service = service
        self.notifier = notifier
        self.send_at = send_at
        self.retry_until = retry_until
        self.bidding_zone = bidding_zone

    async def tick(self, now: datetime) -> str | None:
        local = now.astimezone(self.service.tz)
        day = local.date() + timedelta(days=1)
        if local.time() < self.send_at or await self.service.cache.was_sent(day):
            return None
        plan = await self.service.plan(day)
        if plan.missing_prices:
            if local.time() < self.retry_until:
                return None
            text = format_not_published(f"{day:%a %d %b}", self.bidding_zone)
        else:
            text = format_plan(plan, self.bidding_zone, await self.service.attribution())
        await self.notifier.send(text)
        await self.service.cache.mark_sent(day, now)
        logger.info("Sent the plan for %s", day)
        return text


class Switcher:
    """Keeps every plug in the state the plan asks for right now."""

    def __init__(self, service: PlanService, controller: ShellyController) -> None:
        self.service = service
        self.controller = controller

    async def plans_for(self, now: datetime) -> list[DayPlan]:
        today = now.astimezone(self.service.tz).date()
        plans = []
        for day in (today, today + timedelta(days=1)):
            plan = await self.service.plan(day)
            if plan.missing_prices:
                site = self.service.site
                plan = fallback_plan(site.devices, day, self.service.tz, site.power_cap_kw)
            plans.append(plan)
        return plans

    async def tick(self, now: datetime) -> list[str]:
        return await self.controller.apply(desired_states(await self.plans_for(now), now), now)


async def run_forever(
    name: str,
    tick: Callable[[datetime], Awaitable[object]],
    now: Callable[[], datetime],
    interval_s: float,
) -> None:
    while True:
        try:
            await tick(now())
        except Exception:
            logger.exception("%s round failed", name)
        await asyncio.sleep(interval_s)


async def preview_switching(plan: DayPlan, controller: ShellyController) -> list[str]:
    """Walk through the plan slot by slot and collect what the controller would send."""
    controller.assume_off()
    controller.verbose = False
    lines = []
    for at in slot_starts(plan.horizon_start, plan.horizon_end):
        for action in await controller.apply(desired_states([plan], at), at):
            lines.append(f"{clock(at, plan.tz):>10}  {action}")
    controller.verbose = True
    controller.log = lines[-20:]
    return lines
