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
    # The entries below are pre-seeded from public track maps with
    # *approximate* anchors (S/F-relative). They self-attach when a corner
    # is detected within tolerance; anything that misses just shows a
    # C-number until calibrated from real laps like Monza was.
    "spa": [
        (5.0, "T1 La Source"),
        (12.0, "T3-4 Eau Rouge/Raidillon"),
        (29.0, "T5-6 Les Combes"),
        (34.0, "T7 Malmedy"),
        (37.5, "T8 Bruxelles"),
        (41.0, "T9 Speaker's"),
        (48.0, "T10 Pouhon"),
        (55.0, "T11-12 Fagnes"),
        (60.0, "T13 Stavelot"),
        (65.0, "T14 Courbe Paul Frère"),
        (76.0, "T15-16 Blanchimont"),
        (93.0, "T17-18 Bus Stop"),
    ],
    "sarthe": [
        (3.5, "T1-2 Dunlop Chicane"),
        (8.0, "T3-4 Tertre Rouge"),
        (23.0, "Forza Chicane"),
        (33.0, "Playstation Chicane"),
        (40.0, "T8-9 Mulsanne Corner"),
        (52.0, "T10-11 Indianapolis"),
        (56.0, "T12 Arnage"),
        (73.0, "T13-14 Porsche Curves"),
        (88.0, "Michelin Chicane"),
        (95.0, "Ford Chicanes"),
    ],
    "bahrain": [
        (10.0, "T1-3"),
        (23.0, "T4"),
        (33.0, "T5-7 Esses"),
        (40.0, "T8"),
        (48.0, "T9-10"),
        (60.0, "T11"),
        (68.0, "T12"),
        (74.0, "T13"),
        (85.0, "T14-15"),
    ],
    "imola": [
        (8.0, "T2-4 Tamburello"),
        (18.0, "T5-6 Villeneuve"),
        (23.0, "T7 Tosa"),
        (34.0, "T9-10 Piratella"),
        (45.0, "T11-13 Acque Minerali"),
        (58.0, "T14-15 Variante Alta"),
        (76.0, "T17-18 Rivazza"),
    ],
    "carlos pace": [  # Interlagos
        (6.0, "T1-2 Senna S"),
        (12.0, "T3 Curva do Sol"),
        (32.0, "T4 Descida do Lago"),
        (48.0, "T6-7 Ferradura"),
        (56.0, "T8 Laranja"),
        (65.0, "T9 Pinheirinho"),
        (73.0, "T10 Bico de Pato"),
        (80.0, "T11 Mergulho"),
        (86.0, "T12 Junção"),
    ],
    "fuji": [
        (12.0, "T1"),
        (25.0, "T3 Coca-Cola"),
        (35.0, "T4-5 100R"),
        (45.0, "T6 Advan"),
        (55.0, "T7 Dunlop"),
        (75.0, "T10-12"),
        (90.0, "T13 Panasonic"),
    ],
    "algarve": [  # Portimão
        (8.0, "T1"),
        (15.0, "T3"),
        (25.0, "T5"),
        (40.0, "T8-9"),
        (55.0, "T10-11"),
        (70.0, "T13"),
        (85.0, "T14-15"),
    ],
    "circuit of the americas": [
        (7.0, "T1"),
        (15.0, "T2-6 Esses"),
        (25.0, "T7-9"),
        (33.0, "T11 Hairpin"),
        (55.0, "T12-15"),
        (70.0, "T16-18 Triple"),
        (85.0, "T19-20"),
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
