"""Lap recorder: turns a stream of frames into completed laps.

Watches lap_number; when it increments, the buffered samples become a
LapResult. The first (partial) lap after joining is discarded, as are laps
that touch the pits or cover too little of the track.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from .schema import TelemetryFrame, SessionContext, LapResult, LAP_CHANNELS

logger = logging.getLogger(__name__)

# A lap must cover at least this share of track length to be stored.
MIN_COVERAGE = 0.95


class LapRecorder:
    def __init__(self, on_lap: Callable[[LapResult], None]):
        self.on_lap = on_lap
        self.context = SessionContext()
        self._buffer: dict[str, list] = {ch: [] for ch in LAP_CHANNELS}
        self._current_lap: Optional[int] = None
        self._saw_full_start = False   # buffer began at/near the start line
        self._touched_pits = False
        self._min_dist = float("inf")
        self._max_dist = 0.0
        # Sector splits observed mid-lap. The boundary frame's scoring data
        # can lag (LMU updates it ~5 Hz), so these are the reliable source.
        self._seen_s1 = -1.0
        self._seen_s2 = -1.0
        # Track cuts: the sim drops count_flag below 2 when a lap stops
        # being time-countable. Require a short streak so a single noisy
        # frame can't invalidate a clean lap.
        self._flag_low_streak = 0
        self._cut_detected = False
        # A finished lap parks here until scoring has refreshed (~0.6 s),
        # so last_lap_time/sector reads are fresh, not the previous lap's.
        self._pending: Optional[dict] = None

    def set_context(self, ctx: SessionContext) -> None:
        if ctx.track != self.context.track or ctx.car != self.context.car:
            logger.info("session: %s / %s (%.0f m)", ctx.track, ctx.car, ctx.track_length)
            self.flush()
            self._reset(None)
        self.context = ctx

    def flush(self) -> None:
        """Finalize any parked lap immediately (session change/shutdown)."""
        if self._pending is not None and self._pending.get("frame") is not None:
            self._finalize_pending(self._pending["frame"])

    def feed(self, frame: TelemetryFrame) -> None:
        if self._pending is not None:
            self._pending["countdown"] -= 1
            self._pending["frame"] = frame
            if self._pending["countdown"] <= 0:
                self._finalize_pending(frame)

        if self._current_lap is None:
            self._reset(frame.lap_number)
            self._saw_full_start = frame.lap_dist < 50.0
        elif frame.lap_number == self._current_lap + 1:
            # Only a clean +1 increment is a completed lap crossing the line.
            self._park(frame)
            self._reset(frame.lap_number)
            self._saw_full_start = True  # subsequent laps start at the line
        elif frame.lap_number != self._current_lap:
            # Lap counter reset or jumped (quit to garage, session restart,
            # car reset): the buffered lap never finished — discard it.
            logger.info("lap counter %s -> %s: discarding partial lap",
                        self._current_lap, frame.lap_number)
            self._reset(frame.lap_number)
            self._saw_full_start = frame.lap_dist < 50.0

        if frame.in_pits:
            self._touched_pits = True
        if frame.count_flag < 2:
            self._flag_low_streak += 1
            if self._flag_low_streak >= 15:  # ~0.3 s sustained
                self._cut_detected = True
        else:
            self._flag_low_streak = 0
        self._min_dist = min(self._min_dist, frame.lap_dist)
        self._max_dist = max(self._max_dist, frame.lap_dist)
        if frame.cur_s1 and frame.cur_s1 > 0:
            self._seen_s1 = frame.cur_s1
        if frame.cur_s2 and frame.cur_s2 > 0:
            self._seen_s2 = frame.cur_s2
        for ch in LAP_CHANNELS:
            self._buffer[ch].append(getattr(frame, ch))

    # -- internals ----------------------------------------------------

    def _reset(self, lap_number: Optional[int]) -> None:
        self._buffer = {ch: [] for ch in LAP_CHANNELS}
        self._current_lap = lap_number
        self._touched_pits = False
        self._min_dist = float("inf")
        self._max_dist = 0.0
        self._seen_s1 = -1.0
        self._seen_s2 = -1.0
        self._flag_low_streak = 0
        self._cut_detected = False

    def _park(self, boundary_frame: TelemetryFrame) -> None:
        """Stash the finished lap; finalized ~0.6 s later with fresh scoring."""
        self._pending = {
            "buffer": self._buffer,
            "saw_full_start": self._saw_full_start,
            "touched_pits": self._touched_pits,
            "min_dist": self._min_dist,
            "max_dist": self._max_dist,
            "seen_s1": self._seen_s1,
            "seen_s2": self._seen_s2,
            "cut_detected": self._cut_detected,
            "lap_number": self._current_lap,
            "context": self.context,
            "countdown": 30,
            "frame": boundary_frame,
        }

    def _finalize_pending(self, frame: TelemetryFrame) -> None:
        p, self._pending = self._pending, None
        n = len(p["buffer"]["lap_time"])
        if n < 10:
            return

        # By now (~0.6 s after the line) scoring has refreshed, so the
        # frame's last-lap values describe the lap we parked. Still sanity-
        # check against our own elapsed clock in case scoring never updated
        # (session ended, game paused).
        elapsed = p["buffer"]["lap_time"][-1]
        lap_time = frame.last_lap_time
        official = lap_time is not None and lap_time > 0 and abs(lap_time - elapsed) <= 3.0
        if not official:
            lap_time = elapsed

        track_len = p["context"].track_length or p["max_dist"]
        coverage = (p["max_dist"] - min(p["min_dist"], 0.0)) / max(track_len, 1.0)
        # A lap can only be valid if the sim itself published its time: a lap
        # abandoned at the line (session quit) never gets an official time,
        # so it can never become a personal best.
        valid = (
            official
            and p["saw_full_start"]
            and not p["touched_pits"]
            and not p["cut_detected"]
            and coverage >= MIN_COVERAGE
            and lap_time > 0
        )

        # Fresh scoring first; mid-lap observed splits as fallback.
        s1 = frame.last_s1 if frame.last_s1 and frame.last_s1 > 0 else p["seen_s1"]
        s2 = frame.last_s2 if frame.last_s2 and frame.last_s2 > 0 else p["seen_s2"]
        sectors = []  # rF2 convention: s2 includes s1
        if s1 and s2 and s1 > 0 and s2 > s1 and lap_time > s2:
            sectors = [s1, s2 - s1, lap_time - s2]

        result = LapResult(
            lap_number=p["lap_number"] or 0,
            lap_time=float(lap_time),
            sector_times=[float(s) for s in sectors],
            valid=valid,
            context=p["context"],
            channels={ch: list(vals) for ch, vals in p["buffer"].items()},
        )
        logger.info(
            "lap %d: %.3fs valid=%s samples=%d",
            result.lap_number, result.lap_time, valid, n,
        )
        self.on_lap(result)
