"""Simulated adapter: generates realistic laps on a synthetic circuit.

Exists so the entire pipeline (recording, storage, analysis, UI, overlays)
can be developed and tested without a game running. The model is simple
point-mass physics: corner speed limited by lateral grip, braking and
acceleration limited by fixed envelopes, with per-lap random variation so
consecutive laps differ like a human's would.

Env vars:
  APEX_SIM_TIMESCALE  float, default 1.0 — run faster than real time
  APEX_SIM_SKILL      float 0..1, default 0.85 — driver quality
"""

from __future__ import annotations

import math
import os
import random
from typing import Optional

import numpy as np

from ..schema import TelemetryFrame, SessionContext
from .base import BaseAdapter

# Circuit as (kind, length_m, signed_radius_m); +radius = right turn.
# Sums to ~3.57 km with 360 degrees of total rotation, so the map closes.
_SEGMENTS = [
    ("straight", 700.0, 0.0),
    ("arc", math.pi / 2 * 80, 80.0),      # T1 fast right 90
    ("straight", 220.0, 0.0),
    ("arc", math.pi / 4 * 110, -110.0),   # T2 left kink 45
    ("straight", 380.0, 0.0),
    ("arc", math.pi * 35, 35.0),          # T3 hairpin right 180
    ("straight", 520.0, 0.0),
    ("arc", math.pi / 3 * 55, -55.0),     # T4 chicane left
    ("arc", math.pi / 3 * 55, 55.0),      # T5 chicane right
    ("straight", 320.0, 0.0),
    ("arc", math.pi / 1.8 * 85, 85.0),    # T6 long right 100
    ("straight", 260.0, 0.0),
    ("arc", math.pi / 3.27 * 48, -48.0),  # T7 left 55
    ("straight", 420.0, 0.0),
    ("arc", math.pi / 2 * 75, 75.0),      # T8 right 90 onto main straight
]

V_MAX = 88.0          # m/s top speed (~317 km/h)
A_BRAKE = 32.0        # m/s^2 braking decel at skill 1.0
A_LAT = 22.0          # m/s^2 lateral grip at skill 1.0
GEAR_SPEEDS = [0.0, 26.0, 38.0, 49.0, 59.0, 69.0, 79.0]  # upshift points


def _accel_cap(v: float) -> float:
    """Power-limited acceleration available at speed v."""
    return float(np.clip(14.0 - 0.115 * v, 1.5, 12.0))


class _Track:
    """Precomputed centerline: distance grid -> position, curvature."""

    def __init__(self, step: float = 1.0):
        xs, zs, curvs = [], [], []
        x = z = heading = 0.0
        for kind, length, radius in _SEGMENTS:
            n = max(int(length / step), 2)
            ds = length / n
            for _ in range(n):
                xs.append(x)
                zs.append(z)
                if kind == "arc":
                    curvs.append(1.0 / radius)
                    heading += ds / radius
                else:
                    curvs.append(0.0)
                x += ds * math.cos(heading)
                z += ds * math.sin(heading)
        self.length = float(sum(s[1] for s in _SEGMENTS))
        self.dist = np.linspace(0.0, self.length, len(xs), endpoint=False)
        self.x = np.array(xs)
        self.z = np.array(zs)
        self.curv = np.abs(np.array(curvs))
        self.curv_signed = np.array(curvs)

    def speed_profile(self, a_lat: float, a_brake: float, rng: random.Random) -> np.ndarray:
        """Target speed at every grid point for one lap, with human noise."""
        v_corner = np.where(
            self.curv > 1e-6,
            np.sqrt(a_lat / np.maximum(self.curv, 1e-6)),
            V_MAX,
        )
        v_corner = np.minimum(v_corner, V_MAX)
        # Per-corner speed noise: a human misses the apex a little, differently
        # each lap. Smooth noise so it varies corner-to-corner, not sample-to-sample.
        n = len(v_corner)
        noise = np.interp(
            np.arange(n),
            np.linspace(0, n, 20),
            [1.0 + rng.gauss(0.0, 0.012) for _ in range(20)],
        )
        v = v_corner * noise
        ds = self.length / n
        # Backward pass twice around the loop so braking zones wrap correctly.
        for _ in range(2):
            for i in range(n - 1, -1, -1):
                nxt = (i + 1) % n
                v[i] = min(v[i], math.sqrt(v[nxt] ** 2 + 2 * a_brake * ds))
        # Forward pass twice: acceleration limits.
        for _ in range(2):
            for i in range(n):
                prv = (i - 1) % n
                cap = math.sqrt(v[prv] ** 2 + 2 * _accel_cap(v[prv]) * ds)
                v[i] = min(v[i], cap)
        return v


class SimAdapter(BaseAdapter):
    name = "sim"
    game_title = "Simulated Circuit"
    rate_hz = 50.0

    def __init__(self):
        self.track = _Track()
        self.skill = float(os.environ.get("APEX_SIM_SKILL", "0.85"))
        self.time_scale = float(os.environ.get("APEX_SIM_TIMESCALE", "1.0"))
        self.rng = random.Random()
        self._active = False
        # car state
        self.dist = 0.0
        self.v = 40.0
        self.lap_time = 0.0
        self.lap_number = 1
        self.last_lap = -1.0
        self.best_lap = -1.0
        self.cur_s1 = self.cur_s2 = -1.0
        self.last_s1 = self.last_s2 = -1.0
        self._profile = None
        self._session = SessionContext(
            game="Simulated",
            track="Apex Ring",
            car="Test LMP",
            track_length=self.track.length,
            session_type="practice",
        )

    # -- BaseAdapter --------------------------------------------------

    def connect(self) -> bool:
        self._new_lap_profile()
        self._active = True
        return True

    def disconnect(self) -> None:
        self._active = False

    def is_active(self) -> bool:
        return self._active

    def session(self) -> SessionContext:
        return self._session

    def poll(self) -> Optional[TelemetryFrame]:
        if not self._active:
            return None
        dt = (1.0 / self.rate_hz) * self.time_scale
        self._step(dt)
        return self._frame()

    # -- simulation ---------------------------------------------------

    def _limits(self):
        scale = 0.88 + 0.12 * self.skill
        return A_LAT * scale, A_BRAKE * scale

    def _new_lap_profile(self):
        a_lat, a_brake = self._limits()
        self._profile = self.track.speed_profile(a_lat, a_brake, self.rng)

    def _step(self, dt: float):
        t = self.track
        v_target = float(np.interp(self.dist, t.dist, self._profile, period=t.length))
        # accelerate/brake toward target within capability
        a_lat, a_brake = self._limits()
        if v_target > self.v:
            a = min(_accel_cap(self.v), (v_target - self.v) / dt)
        else:
            a = max(-a_brake, (v_target - self.v) / dt)
        self.v = max(self.v + a * dt, 5.0)
        self.dist += self.v * dt
        self.lap_time += dt
        self._accel = a  # kept for pedal derivation

        s1_line = t.length / 3.0
        s2_line = 2.0 * t.length / 3.0
        prev = self.dist - self.v * dt
        if prev < s1_line <= self.dist:
            self.cur_s1 = self.lap_time
        if prev < s2_line <= self.dist:
            self.cur_s2 = self.lap_time

        if self.dist >= t.length:
            self.dist -= t.length
            self.last_lap = self.lap_time
            self.last_s1, self.last_s2 = self.cur_s1, self.cur_s2
            if self.best_lap < 0 or self.last_lap < self.best_lap:
                self.best_lap = self.last_lap
            self.lap_number += 1
            self.lap_time = self.dist / max(self.v, 1.0)
            self.cur_s1 = self.cur_s2 = -1.0
            self._new_lap_profile()

    def _frame(self) -> TelemetryFrame:
        t = self.track
        a = self._accel
        throttle = float(np.clip(a / _accel_cap(self.v), 0.0, 1.0)) if a >= 0 else 0.0
        _, a_brake = self._limits()
        brake = float(np.clip(-a / a_brake, 0.0, 1.0)) if a < 0 else 0.0
        curv = float(np.interp(self.dist, t.dist, t.curv_signed, period=t.length))
        steering = float(np.clip(curv * 40.0, -1.0, 1.0))
        gear = 1
        for i, thresh in enumerate(GEAR_SPEEDS):
            if self.v >= thresh:
                gear = i + 1
        lo = GEAR_SPEEDS[gear - 1]
        hi = GEAR_SPEEDS[gear] if gear < len(GEAR_SPEEDS) else V_MAX + 5
        rpm = 3800.0 + 4700.0 * (self.v - lo) / max(hi - lo, 1.0)

        sector = 1 if self.dist < t.length / 3 else (2 if self.dist < 2 * t.length / 3 else 3)
        x = float(np.interp(self.dist, t.dist, t.x, period=t.length))
        z = float(np.interp(self.dist, t.dist, t.z, period=t.length))
        return TelemetryFrame(
            timestamp=self.lap_time,  # session clock not needed by consumers yet
            lap_number=self.lap_number,
            lap_time=self.lap_time,
            lap_dist=self.dist,
            pos_x=x, pos_y=0.0, pos_z=z,
            speed=self.v,
            throttle=throttle, brake=brake, clutch=0.0,
            steering=steering,
            gear=gear, rpm=rpm,
            sector=sector,
            last_lap_time=self.last_lap,
            best_lap_time=self.best_lap,
            last_s1=self.last_s1, last_s2=self.last_s2,
            cur_s1=self.cur_s1, cur_s2=self.cur_s2,
            in_pits=False,
        )
