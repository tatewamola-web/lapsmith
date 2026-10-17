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

SPOTTER_PHRASES = ["Car left.", "Car right.", "Three wide, you're in the middle.",
                   "Clear left.", "Clear right.", "Clear all round."]


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
        return self._update((left, right))

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
        if left and right:
            msg = "Three wide, you're in the middle."
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
