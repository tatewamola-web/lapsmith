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
    # School layout: S/F -> full-course T1 -> school link into the final
    # sector just before Gendebien -> Sunset Bend. Only anchors we're sure
    # of are named; the link corners stay sequential until confirmed.
    "sebring school": [
        (17.7, "T1"),
        (84.5, "T17 Sunset Bend"),
    ],
    "monza": [
        (17.0, "T1-2 Variante del Rettifilo"),
        (25.0, "T3 Curva Grande"),
        (37.5, "T4-5 Variante della Roggia"),
        (43.5, "T6 Lesmo 1"),
        (50.5, "T7 Lesmo 2"),
        (68.7, "T8 Ascari 1"),
        (69.3, "T9 Ascari 2"),
        (71.1, "T10 Ascari 3"),
        (90.0, "T11 Parabolica"),
    ],
}


def corner_names_for(track: str) -> list[tuple[float, str]]:
    t = (track or "").lower()
    for key, corners in CORNER_DB.items():
        if key in t:
            return corners
    return []


def assign_names(track: str, apex_pcts: list[float]) -> list[str]:
    """One name per anchor, each claiming only its nearest detected corner —
    so a chicane split into elements doesn't get the same name three times."""
    names = [""] * len(apex_pcts)
    taken: set[int] = set()
    for pct, name in corner_names_for(track):
        best_i, best_d = -1, MATCH_TOLERANCE
        for i, apex in enumerate(apex_pcts):
            if i in taken:
                continue
            d = abs(pct - apex)
            if d < best_d:
                best_i, best_d = i, d
        if best_i >= 0:
            names[best_i] = name
            taken.add(best_i)
    return names
