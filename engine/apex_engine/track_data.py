"""Known-track corner names.

Anchors are % of lap distance at the corner apex, calibrated from real
recorded laps (they depend on where the sim puts the timing line, so they
are measured, not copied from a map). A detected corner within
MATCH_TOLERANCE of an anchor gets its real name; anything else stays "T-n".

Add tracks as they get driven — calibration is just reading apex_pct from
the insights output on a clean lap.
"""

from __future__ import annotations

MATCH_TOLERANCE = 4.0  # percent of lap

# track-name substring (lowercase) -> [(apex_pct, corner name), ...]
CORNER_DB: dict[str, list[tuple[float, str]]] = {
    "monza": [
        (17.0, "T1-2 Variante del Rettifilo"),
        (25.0, "T3 Curva Grande"),
        (37.5, "T4-5 Variante della Roggia"),
        (43.5, "T6 Lesmo 1"),
        (50.5, "T7 Lesmo 2"),
        (69.0, "T8-9-10 Variante Ascari"),
        (90.0, "T11 Parabolica"),
    ],
}


def corner_names_for(track: str) -> list[tuple[float, str]]:
    t = (track or "").lower()
    for key, corners in CORNER_DB.items():
        if key in t:
            return corners
    return []


def match_name(track: str, apex_pct: float) -> str:
    best, best_d = "", MATCH_TOLERANCE
    for pct, name in corner_names_for(track):
        d = abs(pct - apex_pct)
        if d < best_d:
            best, best_d = name, d
    return best
