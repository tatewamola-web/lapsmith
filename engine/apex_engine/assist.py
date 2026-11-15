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

CAR_LENGTH = 6.0   # m — overlap window along travel (car length + ~1 m early pickup)
LAT_MIN = 1.0      # m — closer than this laterally is "same line", not alongside
LAT_MAX = 5.5      # m — beyond this they're not really alongside
HOLD_ON = 0.1      # s — a car appearing alongside: call it almost immediately
HOLD_OFF = 0.4     # s — "clear" waits a little longer so it doesn't flicker

STILL_THERE_AFTER = 2.0   # s alongside before the first "still there"
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
        # gaining a car is urgent; losing one can wait a moment
        hold = HOLD_ON if sum(observed) > sum(self.state) else HOLD_OFF
        if observed == self.state or now - self._candidate_since < hold:
            return None
        prev, self.state = self.state, observed
        left, right = observed
        if any(observed) and not any(prev):
            self._alongside_since = now
            self._reminders = 0
            self._last_reminder = float("-inf")  # first reminder: only the 2 s rule applies
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
        self._pending_since: Optional[float] = None
        self._quiet_until = 0.0
        self._reported_rank = -1
        self._zones_at_start: Optional[list[int]] = None
        self._parts_at_start: Optional[int] = None
        self._max_impact = 0.0
        self._tyre: Optional[tuple[str, int]] = None
        self._lost_part = False
        self._susp_hit: set[int] = set()
        self._engine_ran = False
        self._engine_dead_since: Optional[float] = None
        self._engine_reported = False
        self._energy_at_lap_start: Optional[float] = None
        self._energy_usage: list[float] = []
        self._last_energy_level = None
        voice.prewarm(self.all_pieces())

    # Incident handling: a crash produces a burst of raw events (bounces add
    # dents, parts come off, tyres and suspension break). Collect them
    # briefly, then speak ONE message assembled from short pre-synthesized
    # pieces, worst news first.
    SETTLE = 0.6      # s after the first event: long enough to merge bounces
    QUIET = 10.0      # s after a report: only a worse problem may speak

    # Severity buckets match LMU's own damage colours:
    # light = yellow, medium = orange, heavy = red, broken = gone.
    @staticmethod
    def susp_level(x: float) -> Optional[str]:
        if x >= 0.99:
            return "broken"
        if x >= 0.6:
            return "heavy"
        if x >= 0.3:
            return "medium"
        if x > 0.02:
            return "light"
        return None

    @staticmethod
    def susp_phrase(i: int, level: str) -> str:
        w = _WHEELS[i]
        if level == "broken":
            return f"{w[0].upper() + w[1:]} suspension's broken."
        return f"{level[0].upper() + level[1:]} suspension damage, {w}."

    @classmethod
    def all_pieces(cls) -> list[str]:
        """Every piece an incident report can use, synthesized at startup
        so a report never waits on speech generation (~30 short clips)."""
        out = ["Light damage.", "Medium damage.", "Heavy damage.", "Box this lap.",
               "Engine's gone. Get it off the racing line.", "Engine's running hot."]
        for i in range(4):
            out.append(f"Puncture {_WHEELS[i]}.")
            out.append(f"Lost the {_WHEELS[i]} wheel.")
            out += [cls.susp_phrase(i, lv) for lv in ("light", "medium", "heavy", "broken")]
        return out

    _LEVEL = {None: 0, "light": 1, "medium": 2, "heavy": 3, "broken": 4}

    def incident_active(self) -> bool:
        """True during a crash and 2 s after the report: the spotter stays
        quiet while the car is spinning, then gets straight back to work
        (the 10 s QUIET window only limits further damage reports)."""
        return (self._pending_since is not None
                or time.monotonic() < self._quiet_until - self.QUIET + 2.0)

    def on_frame(self, frame, status: Optional[dict]) -> None:
        if status is None:
            return
        prev, self._prev = self._prev, status
        if frame.lap_number != self._lap:
            self._on_new_lap(frame, status)
        if prev is None:
            return

        for i in range(4):
            if status["wheel_detached"][i] and not prev["wheel_detached"][i]:
                self._incident(tyre=("wheel", i))
            elif status["flat"][i] and not prev["flat"][i]:
                self._incident(tyre=("flat", i))

        # suspension (LMU REST): a corner moving to a worse colour bucket
        if "suspension" in status and "suspension" in prev:
            for i in range(4):
                now_lv = self._LEVEL[self.susp_level(status["suspension"][i])]
                was_lv = self._LEVEL[self.susp_level(prev["suspension"][i])]
                if now_lv > was_lv:
                    self._incident()
                    self._susp_hit.add(i)

        if frame.speed > 20 and self._pending_since is None:
            for i, kpa in enumerate(status["pressure"]):
                self._max_pressure[i] = max(self._max_pressure[i], kpa)
                peak = self._max_pressure[i]
                if (peak > 100 and kpa < peak * 0.8 and not status["flat"][i]
                        and not self._leak_warned[i]):
                    self._leak_warned[i] = True
                    self.voice.say(f"Losing pressure, {_WHEELS[i]}. Might be a slow puncture.")

        if status["dents"] > prev["dents"] or (status["parts_detached"] and not prev["parts_detached"]):
            if self._zones_at_start is None:
                self._zones_at_start = list(prev.get("dent_zones", []))
                self._parts_at_start = prev.get("parts_lost")
            self._incident()
            if status["parts_detached"] and not prev["parts_detached"]:
                self._lost_part = True

        if status["overheating"] and not prev["overheating"]:
            self.voice.say("Engine's running hot.")

        if self._pending_since is not None:
            self._max_impact = max(self._max_impact, status.get("impact", 0.0))
        self._check_engine(frame, status)
        self._maybe_report(status)

    def _check_engine(self, frame, status: dict) -> None:
        """No engine-health value exists in LMU's data, but a dead engine is
        unmistakable: revs collapse while the car is still rolling."""
        now = time.monotonic()
        rpm = status.get("rpm", 0.0)
        if rpm > 1500:
            self._engine_ran = True
            self._engine_dead_since = None
            self._engine_reported = False
            return
        if (self._engine_ran and rpm < 300 and frame.speed > 3 and not frame.in_pits
                and not self._engine_reported):
            if self._engine_dead_since is None:
                self._engine_dead_since = now
            elif now - self._engine_dead_since > 1.5:
                self._engine_reported = True
                self.voice.say_many(["Engine's gone. Get it off the racing line."])

    def _incident(self, tyre: Optional[tuple[str, int]] = None) -> None:
        if self._pending_since is None:
            self._pending_since = time.monotonic()
        if self._prev is not None:
            self._max_impact = max(self._max_impact, self._prev.get("impact", 0.0))
        if tyre and (self._tyre is None or tyre[0] == "wheel"):
            self._tyre = tyre  # a lost wheel outranks a puncture

    # A contact smaller than this is a touch, not damage worth a call.
    # Tuned from logged incidents (see "incident:" lines in engine.log).
    LIGHT_MIN_IMPACT = 400.0

    def _body_severity(self, status: dict) -> Optional[str]:
        """Grade body damage exactly like LMU's damage screen: the worst
        zone that got worse. A zone reaching 1 = yellow (light), 2 = orange
        (medium), a part coming off = red (heavy)."""
        start = self._zones_at_start
        if start is None and not self._lost_part:
            return None
        zones = status.get("dent_zones", [])
        worst = max((z for z, z0 in zip(zones, start or zones) if z > z0), default=0)
        parts_now = status.get("parts_lost")
        parts_gone = self._lost_part or (
            parts_now is not None and self._parts_at_start is not None
            and parts_now > self._parts_at_start)
        if parts_gone:
            severity = "heavy"
        elif worst >= 2:
            severity = "medium"
        elif worst == 1 and self._max_impact >= self.LIGHT_MIN_IMPACT:
            severity = "light"
        else:
            severity = None  # a touch: nothing visible, say nothing
        logger.info("incident: zones %s -> %s, impact %.0f, parts %s -> %s => %s",
                    start, zones, self._max_impact, self._parts_at_start, parts_now, severity)
        return severity

    def _maybe_report(self, status: dict) -> None:
        if self._pending_since is None or time.monotonic() - self._pending_since < self.SETTLE:
            return
        pieces: list[str] = []
        rank = 0
        box = False
        if self._tyre:
            kind, i = self._tyre
            pieces.append(f"Lost the {_WHEELS[i]} wheel." if kind == "wheel" else f"Puncture {_WHEELS[i]}.")
            rank, box = 20, True
        # worst damaged suspension corner(s), at most two
        susp = []
        if "suspension" in status:
            susp = sorted(((self._LEVEL[self.susp_level(status["suspension"][i])], i)
                           for i in self._susp_hit), reverse=True)
        names = {v: k for k, v in self._LEVEL.items()}
        for level, i in susp[:2]:
            if names[level]:
                pieces.append(self.susp_phrase(i, names[level]))
                rank = max(rank, 10 + level)
                box = box or level >= 3
        body = self._body_severity(status)
        if body and len(pieces) < 2:
            pieces.append(f"{body[0].upper() + body[1:]} damage.")
            rank = max(rank, self._LEVEL[body])
            box = box or body == "heavy"
        if pieces and (time.monotonic() >= self._quiet_until or rank > self._reported_rank):
            self.voice.say_many(pieces + (["Box this lap."] if box else []))
            self._reported_rank = rank
            self._quiet_until = time.monotonic() + self.QUIET
        self._pending_since = None
        self._zones_at_start = None
        self._parts_at_start = None
        self._max_impact = 0.0
        self._tyre = None
        self._lost_part = False
        self._susp_hit = set()

    def _on_new_lap(self, frame, status: dict) -> None:
        fuel = status["fuel"]
        if self._fuel_at_lap_start is not None and self._lap >= 0 and not frame.in_pits:
            used = self._fuel_at_lap_start - fuel
            if 0.05 < used < status["fuel_capacity"] * 0.5:  # ignore refuels / junk
                self._usage = (self._usage + [used])[-3:]
        self._check_energy(frame, status)
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

    def _check_energy(self, frame, status: dict) -> None:
        """Virtual energy (LMU REST): same lap-based warnings as fuel. In
        classes that run on virtual energy it's the real limit, not fuel."""
        e, e_max = status.get("energy"), status.get("energy_max")
        if not e or not e_max:
            return
        if self._energy_at_lap_start is not None and self._lap >= 0 and not frame.in_pits:
            used = self._energy_at_lap_start - e
            if 0 < used < e_max * 0.5:
                self._energy_usage = (self._energy_usage + [used])[-3:]
        self._energy_at_lap_start = e
        if not self._energy_usage:
            return
        laps_left = e / (sum(self._energy_usage) / len(self._energy_usage))
        if laps_left < 1.2:
            tier, msg = 1, "Energy is critical. Box this lap."
        elif laps_left < 2.2:
            tier, msg = 2, "Energy's getting low, about two laps left."
        elif laps_left < 3.5:
            tier, msg = 3, f"Energy for about {int(laps_left)} laps."
        else:
            self._last_energy_level = None
            return
        if tier != self._last_energy_level:
            self._last_energy_level = tier
            self.voice.say(msg)
