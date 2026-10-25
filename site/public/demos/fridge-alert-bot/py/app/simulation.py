"""A simple thermal model of a fridge probe, used by simulator.py and the tests.

The probe temperature moves towards a target exponentially (Newton's law of cooling):
    T += (target - T) * (1 - exp(-dt / tau))

* normal      — the compressor holds the setpoint;
* door open   — for 30-120 s the air around the probe gets a few degrees warmer
                (it mixes with room air, it does not become room air);
* failure     — the compressor stops for 15-45 min and the fridge warms towards room
                temperature, slowly, because the food inside has a lot of thermal mass.

A single door opening makes a short spike that should NOT alert; a failure should.
"""

import math
import random
from dataclasses import dataclass
from enum import StrEnum


class Mode(StrEnum):
    NORMAL = "normal"
    DOOR_OPEN = "door_open"
    FAILURE = "failure"


@dataclass(frozen=True)
class SensorProfile:
    sensor_id: str
    setpoint_c: float
    limit_c: float
    ambient_c: float = 24.0
    door_delta_c: float = 5.0  # how much warmer the probe's air gets while the door is open
    door_tau_s: float = 300.0
    cool_tau_s: float = 180.0  # how fast the compressor pulls it back down
    warm_tau_s: float = 3600.0  # how slowly it warms up when the compressor is off


DEFAULT_PROFILES = [
    SensorProfile("kitchen-fridge-1", setpoint_c=3.5, limit_c=5.0),
    SensorProfile("kitchen-fridge-2", setpoint_c=3.0, limit_c=5.0),
    SensorProfile("bar-fridge", setpoint_c=4.5, limit_c=7.0),
    SensorProfile("freezer-1", setpoint_c=-19.0, limit_c=-15.0, warm_tau_s=7200.0),
]


class FridgeModel:
    def __init__(
        self,
        profile: SensorProfile,
        rng: random.Random,
        door_per_hour: float = 3.0,
        failures_per_day: float = 1.0,
    ) -> None:
        self.profile = profile
        self._rng = rng
        self._door_per_s = door_per_hour / 3600
        self._failure_per_s = failures_per_day / 86400
        self.temperature = profile.setpoint_c + rng.uniform(-0.3, 0.3)
        self.mode = Mode.NORMAL
        self._mode_left_s = 0.0

    def force_failure(self, duration_s: float = 20 * 60) -> None:
        self.mode = Mode.FAILURE
        self._mode_left_s = duration_s

    def force_door(self, duration_s: float = 120) -> None:
        self.mode = Mode.DOOR_OPEN
        self._mode_left_s = duration_s

    def _maybe_start_event(self, dt: float) -> None:
        roll = self._rng.random()
        if roll < self._failure_per_s * dt:
            self.force_failure(self._rng.uniform(15 * 60, 45 * 60))
        elif roll < (self._failure_per_s + self._door_per_s) * dt:
            self.force_door(self._rng.uniform(30, 120))

    def step(self, dt: float) -> float:
        """Advance the model by `dt` seconds and return the new temperature."""
        if self.mode is Mode.NORMAL:
            self._maybe_start_event(dt)

        p = self.profile
        if self.mode is Mode.NORMAL:
            target, tau = p.setpoint_c, p.cool_tau_s
        elif self.mode is Mode.DOOR_OPEN:
            target, tau = p.setpoint_c + p.door_delta_c, p.door_tau_s
        else:
            target, tau = p.ambient_c, p.warm_tau_s

        self.temperature += (target - self.temperature) * (1 - math.exp(-dt / tau))
        self.temperature += self._rng.gauss(0, 0.05)  # sensor noise

        if self.mode is not Mode.NORMAL:
            self._mode_left_s -= dt
            if self._mode_left_s <= 0:
                self.mode = Mode.NORMAL
        return round(self.temperature, 2)
