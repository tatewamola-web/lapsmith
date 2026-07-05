"""Lap comparison math.

The core idea: laps are compared **by track position, not by time**.
Two drivers reach the same corner at different times, so plotting both
against distance-around-track lines their corners up. The time-delta
curve is then:

    delta(d) = t_lap(d) - t_ref(d)

where t(d) is the time each lap first reached distance d. Where the
curve's slope rises, you are losing time; where it falls, you're gaining.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

GRID_STEP = 4.0  # meters between comparison points


def _monotonic(dist: np.ndarray, *channels: np.ndarray):
    """Strip samples where lap_dist goes backwards (grid/jump noise).

    Scoring-lag guard: sims that publish lap distance at a low rate (LMU's
    scoring buffer is ~5 Hz) can leave the previous lap's near-full distance
    on the first frames after the line. Without trimming, the cummax filter
    below would discard the entire lap. Start from the minimum distance seen
    in the first ~2 s of samples.
    """
    lead = min(len(dist), 120)
    start = int(np.argmin(dist[:lead]))
    dist = dist[start:]
    channels = tuple(c[start:] for c in channels)
    keep = np.maximum.accumulate(dist) <= dist
    # ensure strictly increasing for interp
    d = dist[keep]
    uniq = np.concatenate(([True], np.diff(d) > 0))
    return (d[uniq],) + tuple(c[keep][uniq] for c in channels)


def resample_lap(channels: dict[str, np.ndarray], grid: np.ndarray) -> dict[str, np.ndarray]:
    """Interpolate every channel onto a common distance grid."""
    names = [k for k in channels if k != "lap_dist"]
    d, *chans = _monotonic(channels["lap_dist"], *[channels[k] for k in names])
    out = {"lap_dist": grid}
    for name, ch in zip(names, chans):
        out[name] = np.interp(grid, d, ch)
    return out


def compare(lap: dict[str, np.ndarray], ref: dict[str, np.ndarray]) -> Optional[dict]:
    """Build the full comparison payload for two laps' channel dicts."""
    if "lap_dist" not in lap or "lap_dist" not in ref:
        return None
    max_d = float(min(lap["lap_dist"].max(), ref["lap_dist"].max()))
    if max_d < GRID_STEP * 10:
        return None
    grid = np.arange(0.0, max_d, GRID_STEP)

    a = resample_lap(lap, grid)
    b = resample_lap(ref, grid)
    delta = a["lap_time"] - b["lap_time"]
    # Zero the delta at the start line: only relative progression matters.
    delta = delta - delta[0]

    round3 = lambda arr: [round(float(v), 3) for v in arr]
    return {
        "dist": round3(grid),
        "delta": round3(delta),
        "lap": {
            "speed": round3(a["speed"]),
            "throttle": round3(a["throttle"]),
            "brake": round3(a["brake"]),
            "steering": round3(a["steering"]),
            "gear": [int(v) for v in np.round(a["gear"])],
        },
        "ref": {
            "speed": round3(b["speed"]),
            "throttle": round3(b["throttle"]),
            "brake": round3(b["brake"]),
            "steering": round3(b["steering"]),
            "gear": [int(v) for v in np.round(b["gear"])],
        },
        # Track map from the reference lap's world position, with the
        # delta at each point so the UI can color where time is lost.
        "map": {
            "x": round3(b["pos_x"]),
            "z": round3(b["pos_z"]),
        },
    }


def lap_channels_payload(channels: dict[str, np.ndarray]) -> dict:
    """Single-lap payload resampled to the grid (for viewing one lap)."""
    max_d = float(channels["lap_dist"].max())
    grid = np.arange(0.0, max_d, GRID_STEP)
    a = resample_lap(channels, grid)
    return {k: [round(float(v), 3) for v in arr] for k, arr in a.items()}
