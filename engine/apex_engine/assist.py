"""In-car assistance that runs inside the engine loop: spoken corner
callouts and the (beta) spotter. Both speak through voice.Voice.

They live in the engine rather than a widget so they work whether or not
any widget window is open — audio is its own output channel.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from typing import Callable, Optional

from .voice import Voice, speakable_callout

logger = logging.getLogger(__name__)


class CalloutSpeaker:
    """Speaks each corner's callout once per lap, timed so the sentence
    finishes before the braking zone rather than in it."""

    def __init__(self, voice: Voice, coach_for: Callable[[str, str, str], dict]):
        self.voice = voice
        self.coach_for = coach_for
        self.callouts: list[dict] = []
        self._key = ""
        self._fetched_at = 0.0
        self._loading = False
        self._spoken: set[int] = set()
        self._lap = -1

    def _refresh(self, track: str, car_class: str, car: str) -> None:
        """Recompute callouts off-thread (the coach fits models — too slow
        for the 50 Hz loop)."""
        key = f"{track}|{car_class or car}"
        if self._loading or (key == self._key and time.monotonic() - self._fetched_at < 180):
            return
        self._loading = True

        def run():
            try:
                result = self.coach_for(track, car_class, car)
                self.callouts = result.get("callouts", [])
                self._key = key
                self._fetched_at = time.monotonic()
                self.voice.prewarm([speakable_callout(c["corner"], c["text"])
                                    for c in self.callouts])
                logger.info("callouts: %d for %s", len(self.callouts), key)
            except Exception:
                logger.exception("callouts: refresh failed")
            finally:
                self._loading = False

        threading.Thread(target=run, daemon=True, name="callouts").start()

    def on_frame(self, frame, session, lead: float) -> None:
        self._refresh(session.track, session.car_class, session.car)
        if frame.lap_number != self._lap:
            self._lap = frame.lap_number
            self._spoken.clear()
        if frame.in_pits or frame.speed < 10:
            return
        # a spoken callout takes ~2.5s: start early enough that it's done
        # before the corner, whatever the user's on-screen lead setting is
        trigger = max(lead, frame.speed * 3.5)
        for i, c in enumerate(self.callouts):
            if i in self._spoken:
                continue
            ahead = c["apex_dist"] - frame.lap_dist
            if 0 < ahead <= trigger:
                self._spoken.add(i)
                self.voice.say(speakable_callout(c["corner"], c["text"]))
                break


# --- spotter ----------------------------------------------------------------

CAR_LENGTH = 5.0   # m — overlap window along the car's direction of travel
LAT_MIN = 1.0      # m — closer than this laterally is "same line", not alongside
LAT_MAX = 5.5      # m — beyond this they're not really alongside
HOLD = 0.35        # s — a state must persist this long before it's announced

STILL_THERE_AFTER = 2.5   # s alongside before the first "still there"
STILL_THERE_EVERY = 3.0   # s between repeats
STILL_THERE_MAX = 3       # don't nag forever in a long side-by-side fight

SPOTTER_PHRASES = ["Car left.", "Car right.", "Three wide, you're in the middle. Hold your line.",
                   "Clear left.", "Clear right.", "Clear all round.",
                   "Still there.", "Still there, hold your line."]


class Spotter:
    """Beta: announces cars alongside — "Car left", "Clear right", "Three wide".

    Geometry: heading comes from the player's own recent movement; each
    nearby car is projected onto that heading (along-track) and its normal
    (side-to-side). Side sign was calibrated from 13,400 recorded samples:
    in LMU's world coordinates, steering right rotates the heading toward
    the negative cross-product side, so a negative cross means "right".
    """

    def __init__(self, voice: Voice):
        self.voice = voice
        self._trail: list[tuple[float, float]] = []
        self.state = (False, False)        # (left, right) currently announced
        self._candidate = (False, False)
        self._candidate_since = 0.0
        self._alongside_since = 0.0
        self._last_reminder = 0.0
        self._reminders = 0
        voice.prewarm(SPOTTER_PHRASES)

    def heading(self) -> Optional[tuple[float, float]]:
        if len(self._trail) < 6:
            return None
        (x0, z0), (x1, z1) = self._trail[0], self._trail[-1]
        d = math.hypot(x1 - x0, z1 - z0)
        if d < 1.0:  # barely moving: heading unreliable
            return None
        return (x1 - x0) / d, (z1 - z0) / d

    def on_frame(self, nearby) -> Optional[str]:
        if nearby is None:
            return None
        me, others = nearby
        self._trail.append(me)
        if len(self._trail) > 8:
            self._trail.pop(0)
        f = self.heading()
        if f is None:
            return None
        fx, fz = f
        left = right = False
        for ox, oz in others:
            rx, rz = ox - me[0], oz - me[1]
            along = fx * rx + fz * rz
            side = -(fx * rz - fz * rx)  # + = right (calibrated sign)
            if abs(along) < CAR_LENGTH and LAT_MIN < abs(side) < LAT_MAX:
                if side > 0:
                    right = True
                else:
                    left = True
        return self._update((left, right)) or self._reminder()

    def _reminder(self) -> Optional[str]:
        """While a car stays alongside: "Still there, hold your line", then
        "Still there" every few seconds, a few times at most."""
        if not any(self.state) or self.state == (True, True):
            return None  # three-wide already carried "hold your line"
        now = time.monotonic()
        if now - self._alongside_since < STILL_THERE_AFTER:
            return None
        if self._reminders >= STILL_THERE_MAX or now - self._last_reminder < STILL_THERE_EVERY:
            return None
        msg = "Still there, hold your line." if self._reminders == 0 else "Still there."
        self._reminders += 1
        self._last_reminder = now
        self.voice.say(msg, urgent=True)
        return msg

    def _update(self, observed: tuple[bool, bool]) -> Optional[str]:
        now = time.monotonic()
        if observed != self._candidate:
            self._candidate = observed
            self._candidate_since = now
            return None
        if observed == self.state or now - self._candidate_since < HOLD:
            return None
        prev, self.state = self.state, observed
        left, right = observed
        if any(observed) and not any(prev):
            self._alongside_since = now
            self._reminders = 0
            self._last_reminder = now
        if left and right:
            msg = "Three wide, you're in the middle. Hold your line."
        elif left and not prev[0]:
            msg = "Car left."
        elif right and not prev[1]:
            msg = "Car right."
        elif not left and not right:
            msg = "Clear all round." if prev[0] and prev[1] else (
                "Clear left." if prev[0] else "Clear right.")
        elif not left and prev[0]:
            msg = "Clear left."
        else:
            msg = "Clear right."
        self.voice.say(msg, urgent=True)
        return msg


# --- engineer: car health -----------------------------------------------------

_WHEELS = ["front left", "front right", "rear left", "rear right"]


class Engineer:
    """Speaks up about the car: fuel running low, punctures and slow leaks,
    lost wheels and parts, contact damage, overheating. Each event is said
    once (fuel at most once per lap) — an engineer, not an alarm."""

    def __init__(self, voice: Voice):
        self.voice = voice
        self._prev: Optional[dict] = None
        self._lap = -1
        self._fuel_at_lap_start: Optional[float] = None
        self._usage: list[float] = []
        self._max_pressure = [0.0] * 4
        self._leak_warned = [False] * 4
        self._last_fuel_level = None  # which warning tier was last spoken

    def on_frame(self, frame, status: Optional[dict]) -> None:
        if status is None:
            return
        prev, self._prev = self._prev, status
        if frame.lap_number != self._lap:
            self._on_new_lap(frame, status)
        if prev is None:
            return
        say = self.voice.say

        for i in range(4):
            if status["wheel_detached"][i] and not prev["wheel_detached"][i]:
                say(f"You've lost the {_WHEELS[i]} wheel. Get it back to the pits.", urgent=True)
            elif status["flat"][i] and not prev["flat"][i]:
                say(f"Puncture, {_WHEELS[i]}. Box this lap.", urgent=True)

        # slow leak: pressure well below what this tyre ran earlier in the stint
        if frame.speed > 20:
            for i, kpa in enumerate(status["pressure"]):
                self._max_pressure[i] = max(self._max_pressure[i], kpa)
                peak = self._max_pressure[i]
                if (peak > 100 and kpa < peak * 0.8 and not status["flat"][i]
                        and not self._leak_warned[i]):
                    self._leak_warned[i] = True
                    say(f"You're losing pressure in the {_WHEELS[i]}. Might be a slow puncture.")

        if status["parts_detached"] and not prev["parts_detached"]:
            say("You've lost a part off the car.")
        elif status["dents"] > prev["dents"]:
            jump = status["dents"] - prev["dents"]
            if status["dents"] >= 6 or jump >= 3:
                say("That's heavy damage. Check the car.")
            else:
                say("Contact. You've picked up some damage.")

        if status["overheating"] and not prev["overheating"]:
            say("Engine's running hot. Get some air to it.")

    def _on_new_lap(self, frame, status: dict) -> None:
        fuel = status["fuel"]
        if self._fuel_at_lap_start is not None and self._lap >= 0 and not frame.in_pits:
            used = self._fuel_at_lap_start - fuel
            if 0.05 < used < status["fuel_capacity"] * 0.5:  # ignore refuels / junk
                self._usage = (self._usage + [used])[-3:]
        self._lap = frame.lap_number
        self._fuel_at_lap_start = fuel
        if not self._usage or status["fuel_capacity"] <= 0:
            return
        per_lap = sum(self._usage) / len(self._usage)
        laps_left = fuel / per_lap
        if laps_left < 1.2:
            tier, msg = 1, "Fuel is critical. Box this lap."
        elif laps_left < 2.2:
            tier, msg = 2, "Fuel's getting low, about two laps left."
        elif laps_left < 3.5:
            tier, msg = 3, f"Fuel for about {int(laps_left)} laps."
        else:
            self._last_fuel_level = None
            return
        if tier != self._last_fuel_level:
            self._last_fuel_level = tier
            self.voice.say(msg)
