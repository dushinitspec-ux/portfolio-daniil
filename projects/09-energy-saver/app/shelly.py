"""Switch Shelly smart plugs through their local HTTP API. DRY-RUN by default.

Gen2 and newer (Plus, Pro, Gen3, Gen4):  GET http://<ip>/rpc/Switch.Set?id=0&on=true
Gen1 (Plug S, Shelly 1):                 GET http://<ip>/relay/0?turn=on

Every ON command carries a flip-back timer (`toggle_after` / `timer`) that ends with the
planned block. If this program crashes or loses the network, the plug still switches
itself off on time instead of running the boiler all day.

In dry-run mode nothing is sent; the exact request is logged instead.
"""

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

import httpx

from app.devices import Device, ShellyPlug
from app.planner import DayPlan

logger = logging.getLogger("energy.shelly")

# The flip-back timer runs a little past the block end, so a late OFF command never races it.
TIMER_MARGIN = timedelta(minutes=2)


def command_url(plug: ShellyPlug, on: bool, seconds: int | None = None) -> str:
    if plug.generation == 1:
        url = f"http://{plug.host}/relay/{plug.channel}?turn={'on' if on else 'off'}"
        return f"{url}&timer={seconds}" if on and seconds else url
    url = f"http://{plug.host}/rpc/Switch.Set?id={plug.channel}&on={'true' if on else 'false'}"
    return f"{url}&toggle_after={seconds}" if on and seconds else url


@dataclass(frozen=True)
class Desired:
    on: bool
    until: datetime | None = None  # end of the current block when on


def desired_states(plans: Iterable[DayPlan], now: datetime) -> dict[str, Desired]:
    """ON when `now` is inside a planned block of any of the plans (today's plan and
    tomorrow's: a night window of tomorrow's plan starts this evening)."""
    states: dict[str, Desired] = {}
    for plan in plans:
        for item in plan.devices:
            block = next((b for b in item.blocks if b.start <= now < b.end), None)
            if block is not None:
                states[item.device.name] = Desired(True, block.end)
            else:
                states.setdefault(item.device.name, Desired(False))
    return states


class ShellyController:
    """Sends a command only when a device's desired state changes."""

    def __init__(
        self, http: httpx.AsyncClient | None, devices: list[Device], dry_run: bool = True
    ) -> None:
        if http is None and not dry_run:
            raise ValueError("switching real plugs needs an HTTP client")
        self._http = http
        self._devices = {d.name: d for d in devices if d.shelly is not None}
        self.dry_run = dry_run
        self.verbose = True  # log every action; a preview turns this off and prints its own
        self._last: dict[str, bool] = {}
        self.log: list[str] = []  # recent actions, newest last

    def assume_off(self) -> None:
        """Treat every plug as already off (for a preview that should not start with a
        round of OFF commands)."""
        self._last = dict.fromkeys(self._devices, False)

    async def apply(self, states: dict[str, Desired], now: datetime) -> list[str]:
        actions: list[str] = []
        for name, device in self._devices.items():
            want = states.get(name, Desired(False))
            if self._last.get(name) == want.on:
                continue
            seconds = None
            if want.on and want.until is not None:
                seconds = int((want.until - now + TIMER_MARGIN).total_seconds())
            assert device.shelly is not None
            url = command_url(device.shelly, want.on, seconds)
            action = f"{name} {'ON' if want.on else 'OFF'}: GET {url}"
            if self.dry_run:
                if self.verbose:
                    logger.info("DRY-RUN %s", action)
                actions.append(f"DRY-RUN {action}")
            else:
                assert self._http is not None
                try:
                    response = await self._http.get(url, timeout=5)
                    response.raise_for_status()
                except httpx.HTTPError as exc:
                    logger.error("Shelly %s (%s) failed: %s", name, device.shelly.host, exc)
                    continue  # _last stays unchanged, so the next round tries again
                logger.info("%s", action)
                actions.append(action)
            self._last[name] = want.on
        self.log = (self.log + actions)[-20:]
        return actions
