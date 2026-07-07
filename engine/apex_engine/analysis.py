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
    payload_channels = lambda ch: {
        "speed": round3(ch["speed"]),
        "throttle": round3(ch["throttle"]),
        "brake": round3(ch["brake"]),
        "steering": round3(ch["steering"]),
        "gear": [int(v) for v in np.round(ch["gear"])],
        # absolute time at each distance point — the playback clock
        "lap_time": round3(ch["lap_time"]),
    }
    result = {
        "dist": round3(grid),
        "delta": round3(delta),
        "lap": payload_channels(a),
        "ref": payload_channels(b),
        # World positions for both laps: the reference line colors the
        # gain/loss map, and the pair together is the racing-line overlay.
        "map": {
            "x": round3(b["pos_x"]),
            "z": round3(b["pos_z"]),
            "you_x": round3(a["pos_x"]),
            "you_z": round3(a["pos_z"]),
        },
    }
    # Track width where recorded (newer laps carry mTrackEdge): total edge-to-
    # edge width ~ 2x the center-to-edge distance. Older laps fall back to a
    # constant in the UI.
    if "track_edge" in b:
        width = np.clip(np.abs(b["track_edge"]) * 2.0, 6.0, 30.0)
        result["map"]["width"] = round3(_smooth(width, 15))
    return result


def _smooth(a: np.ndarray, w: int = 7) -> np.ndarray:
    # Edge-replicate before convolving: plain mode="same" zero-pads, which
    # drags values near the array ends toward 0 — for speed that fakes a
    # braking zone at the start/finish line, for coordinates a fake kink.
    pad = w // 2
    padded = np.pad(np.asarray(a, dtype=float), pad, mode="edge")
    return np.convolve(padded, np.ones(w) / w, mode="valid")


def _find_corner_apexes(dist: np.ndarray, speed: np.ndarray) -> list[int]:
    """Fallback: apexes as prominent local minima of smoothed speed."""
    v = _smooth(speed)
    n = len(v)
    win = 12  # +/- ~50 m at 4 m grid
    apexes: list[int] = []
    for i in range(win, n - win):
        seg = v[i - win:i + win + 1]
        if v[i] != seg.min():
            continue
        # prominence: must actually slow down vs. surroundings
        wide = v[max(0, i - 60):min(n, i + 60)]
        if wide.max() - v[i] < 5.0:  # < 18 km/h dip is not a corner
            continue
        if apexes and dist[i] - dist[apexes[-1]] < 90.0:
            if v[i] < v[apexes[-1]]:
                apexes[-1] = i
            continue
        apexes.append(i)
    return apexes


def _find_corner_apexes_geo(ch: dict[str, np.ndarray]) -> list[int]:
    """Apexes from track geometry: sustained curvature of the driven path.

    Curvature k = |x'z'' - z'x''| / (x'^2 + z'^2)^1.5 — coordinate-free, so
    it finds every real corner including flat-out ones that never show a
    speed dip. Within each curved region the apex is the slowest point
    (or max curvature if speed never dips).
    """
    if "pos_x" not in ch or "pos_z" not in ch:
        return []
    xr, zr = np.asarray(ch["pos_x"], dtype=float), np.asarray(ch["pos_z"], dtype=float)
    n0 = len(xr)
    # A lap is a closed loop: pad with wrap-around BEFORE smoothing and
    # differentiating, so corners at the start/finish line are seen with
    # real neighboring data instead of edge artifacts.
    pad = 40
    closed = bool(np.hypot(xr[0] - xr[-1], zr[0] - zr[-1]) < 40.0) and n0 > 2 * pad
    if closed:
        xr = np.concatenate([xr[-pad:], xr, xr[:pad]])
        zr = np.concatenate([zr[-pad:], zr, zr[:pad]])
    x, z = _smooth(xr, 9), _smooth(zr, 9)
    dx, dz = np.gradient(x), np.gradient(z)
    ddx, ddz = np.gradient(dx), np.gradient(dz)
    k = np.abs(dx * ddz - dz * ddx) / ((dx * dx + dz * dz) ** 1.5 + 1e-12)
    k = _smooth(k, 9)
    if closed:
        k = k[pad:-pad]

    in_corner = k > (1.0 / 320.0)  # radius under ~320 m counts as a corner
    # group contiguous curved stretches, bridging gaps < 40 m (10 pts)
    regions: list[tuple[int, int]] = []
    i, n = 0, len(k)
    while i < n:
        if in_corner[i]:
            j = i
            gap = 0
            end = i
            while j < n and gap < 10:
                if in_corner[j]:
                    end = j
                    gap = 0
                else:
                    gap += 1
                j += 1
            if end - i >= 8:  # at least ~32 m of sustained curvature
                regions.append((i, end))
            i = j
        else:
            i += 1
    # Without wrap-around the first/last samples get phantom curvature from
    # the smoothing window edges — drop regions hugging the line.
    if not closed:
        edge = max(int(n * 0.012), 4)
        regions = [(a, b) for a, b in regions if a > edge and b < n - edge]

    # A region can span a whole complex (chicane, linked corners). Split it
    # at distinct curvature peaks: local maxima at least 60 m apart with a
    # genuine valley between them.
    split: list[tuple[int, int]] = []
    for a, b in regions:
        peaks = [
            i for i in range(a + 2, b - 1)
            if k[i] == k[max(a, i - 8):min(b, i + 8) + 1].max() and k[i] > 1.0 / 320.0
        ]
        kept: list[int] = []
        for p in peaks:
            if not kept:
                kept.append(p)
                continue
            prev = kept[-1]
            valley = k[prev:p + 1].min()
            if p - prev >= 15 and valley < 0.6 * min(k[prev], k[p]):
                kept.append(p)
            elif k[p] > k[prev]:
                kept[-1] = p
        if len(kept) <= 1:
            split.append((a, b))
        else:
            bounds = [a] + [int(np.argmin(k[kept[i]:kept[i + 1] + 1])) + kept[i]
                            for i in range(len(kept) - 1)] + [b]
            for i in range(len(kept)):
                split.append((bounds[i], bounds[i + 1]))

    speed = _smooth(ch["speed"])
    apexes = []
    edge = max(int(n * 0.015), 6)
    for a, b in split:
        seg_v = speed[a:b + 1]
        # slowest point if the corner actually slows the car, else max curvature
        if seg_v.max() - seg_v.min() > 3.0:
            apex = a + int(np.argmin(seg_v))
        else:
            apex = a + int(np.argmax(k[a:b + 1]))
        # The wrap seam joins two different driven lines at the S/F line,
        # which can fake a kink there. A corner hugging the line is only
        # real if speed dips *at the apex itself* (local prominence), not
        # somewhere else in the region.
        if apex < edge or apex > n - edge:
            w0, w1 = max(apex - 15, 0), min(apex + 15, n - 1)
            if speed[w0:w1 + 1].max() - speed[apex] < 8.0:
                continue
        apexes.append(apex)
    return sorted(set(apexes))


def insights(lap: dict[str, np.ndarray], ref: dict[str, np.ndarray],
             ref_s1: float = -1.0, ref_s2: float = -1.0,
             track: str = "") -> Optional[dict]:
    """Corner-by-corner comparison with generated coaching advice.

    Corners are detected on the *reference* lap (the target line). For each
    corner: time lost/gained across it, braking point, apex speed, and
    throttle-application point for both laps.
    """
    if "lap_dist" not in lap or "lap_dist" not in ref:
        return None
    max_d = float(min(lap["lap_dist"].max(), ref["lap_dist"].max()))
    if max_d < GRID_STEP * 10:
        return None
    grid = np.arange(0.0, max_d, GRID_STEP)
    a = resample_lap(lap, grid)   # your lap
    b = resample_lap(ref, grid)   # reference
    delta = a["lap_time"] - b["lap_time"]
    delta -= delta[0]

    # Sector line distances: where the ref lap's clock hit its splits.
    # ref_s2 is cumulative (rF2 convention: includes s1).
    s1_dist = float(np.interp(ref_s1, b["lap_time"], grid)) if ref_s1 > 0 else -1.0
    s2_dist = float(np.interp(ref_s2, b["lap_time"], grid)) if ref_s2 > 0 else -1.0

    def sector_of(d: float) -> int:
        if s1_dist > 0 and d < s1_dist:
            return 1
        if s2_dist > 0 and d < s2_dist:
            return 2
        return 3 if s2_dist > 0 else 0

    # Geometry first (finds every real corner from the driven path);
    # speed-minima fallback when position data is missing.
    apexes = _find_corner_apexes_geo(b) or _find_corner_apexes(grid, b["speed"])
    n = len(grid)
    from .track_data import assign_names
    corner_names = assign_names(track, [float(grid[a]) / max_d * 100 for a in apexes])
    corners = []
    for ci, apex in enumerate(apexes):
        prev_apex = apexes[ci - 1] if ci > 0 else 0
        next_apex = apexes[ci + 1] if ci + 1 < len(apexes) else n - 1
        start = (prev_apex + apex) // 2 if ci > 0 else max(apex - 60, 0)
        end = (apex + next_apex) // 2 if ci + 1 < len(apexes) else min(apex + 60, n - 1)

        def brake_point(ch) -> float:
            zone = np.where(ch["brake"][start:apex + 1] > 0.4)[0]
            return float(grid[start + zone[0]]) if len(zone) else -1.0

        def throttle_on(ch) -> float:
            zone = np.where(ch["throttle"][apex:end + 1] > 0.9)[0]
            return float(grid[apex + zone[0]]) if len(zone) else -1.0

        loss = float(delta[end] - delta[start])
        apex_kmh_you = float(a["speed"][max(start, apex - 6):apex + 7].min() * 3.6)
        apex_kmh_ref = float(b["speed"][max(start, apex - 6):apex + 7].min() * 3.6)
        bp_you, bp_ref = brake_point(a), brake_point(b)
        to_you, to_ref = throttle_on(a), throttle_on(b)

        advice = []
        if loss > 0.03:
            if bp_you > 0 and bp_ref > 0 and bp_you - bp_ref < -12:
                advice.append(f"braking {abs(bp_you - bp_ref):.0f}m earlier than the reference")
            elif bp_you > 0 and bp_ref > 0 and bp_you - bp_ref > 12:
                advice.append(f"braking {bp_you - bp_ref:.0f}m later — likely overshooting")
            if apex_kmh_you < apex_kmh_ref - 3:
                advice.append(f"carrying {apex_kmh_ref - apex_kmh_you:.0f} km/h less at the apex")
            if to_you > 0 and to_ref > 0 and to_you - to_ref > 12:
                advice.append(f"back to full throttle {to_you - to_ref:.0f}m later")
            if not advice:
                advice.append("time drips away through the whole corner — check your line")
        elif loss < -0.03:
            advice.append("faster than the reference here — this corner is a strength")

        apex_pct = round(float(grid[apex]) / max_d * 100, 1)
        corners.append({
            "n": ci + 1,
            "name": corner_names[ci],
            "apex_dist": round(float(grid[apex]), 1),
            "apex_pct": apex_pct,
            "sector": sector_of(float(grid[apex])),
            "loss": round(loss, 3),
            "apex_kmh_you": round(apex_kmh_you, 1),
            "apex_kmh_ref": round(apex_kmh_ref, 1),
            "brake_you": round(bp_you, 1),
            "brake_ref": round(bp_ref, 1),
            "advice": "; ".join(advice) if advice else "even with the reference",
        })

    worst = sorted([c for c in corners if c["loss"] > 0.03],
                   key=lambda c: -c["loss"])[:3]
    return {
        "corners": corners,
        "worst": [c["n"] for c in worst],
        "s1_dist": round(s1_dist, 1),
        "s2_dist": round(s2_dist, 1),
        "total_delta": round(float(delta[-1]), 3),
        "corner_loss_total": round(sum(c["loss"] for c in corners if c["loss"] > 0), 3),
    }


def lap_channels_payload(channels: dict[str, np.ndarray]) -> dict:
    """Single-lap payload resampled to the grid (for viewing one lap)."""
    max_d = float(channels["lap_dist"].max())
    grid = np.arange(0.0, max_d, GRID_STEP)
    a = resample_lap(channels, grid)
    return {k: [round(float(v), 3) for v in arr] for k, arr in a.items()}
