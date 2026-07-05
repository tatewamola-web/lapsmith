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

    def set_context(self, ctx: SessionContext) -> None:
        if ctx.track != self.context.track or ctx.car != self.context.car:
            logger.info("session: %s / %s (%.0f m)", ctx.track, ctx.car, ctx.track_length)
            self._reset(None)
        self.context = ctx

    def feed(self, frame: TelemetryFrame) -> None:
        if self._current_lap is None:
            self._reset(frame.lap_number)
            self._saw_full_start = frame.lap_dist < 50.0
        elif frame.lap_number != self._current_lap:
            self._finalize(frame)
            self._reset(frame.lap_number)
            self._saw_full_start = True  # subsequent laps start at the line

        if frame.in_pits:
            self._touched_pits = True
        self._min_dist = min(self._min_dist, frame.lap_dist)
        self._max_dist = max(self._max_dist, frame.lap_dist)
        for ch in LAP_CHANNELS:
            self._buffer[ch].append(getattr(frame, ch))

    # -- internals ----------------------------------------------------

    def _reset(self, lap_number: Optional[int]) -> None:
        self._buffer = {ch: [] for ch in LAP_CHANNELS}
        self._current_lap = lap_number
        self._touched_pits = False
        self._min_dist = float("inf")
        self._max_dist = 0.0

    def _finalize(self, boundary_frame: TelemetryFrame) -> None:
        n = len(self._buffer["lap_time"])
        if n < 10:
            return

        # The frame after the line carries the authoritative completed-lap
        # times from the sim's own scoring.
        lap_time = boundary_frame.last_lap_time
        if lap_time is None or lap_time <= 0:
            lap_time = self._buffer["lap_time"][-1]

        track_len = self.context.track_length or self._max_dist
        coverage = (self._max_dist - min(self._min_dist, 0.0)) / max(track_len, 1.0)
        valid = (
            self._saw_full_start
            and not self._touched_pits
            and coverage >= MIN_COVERAGE
            and lap_time > 0
        )

        s1 = boundary_frame.last_s1
        s2 = boundary_frame.last_s2  # rF2 convention: s2 includes s1
        sectors = []
        if s1 and s2 and s1 > 0 and s2 > s1 and lap_time > s2:
            sectors = [s1, s2 - s1, lap_time - s2]

        result = LapResult(
            lap_number=self._current_lap or 0,
            lap_time=float(lap_time),
            sector_times=[float(s) for s in sectors],
            valid=valid,
            context=self.context,
            channels={ch: list(vals) for ch, vals in self._buffer.items()},
        )
        logger.info(
            "lap %d: %.3fs valid=%s samples=%d",
            result.lap_number, result.lap_time, valid, n,
        )
        self.on_lap(result)
