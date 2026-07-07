"""Import lap history from LMU's session result logs.

The rF2 engine writes a results XML after every session
(UserData/Log/Results/*.xml) with every driver's lap and sector times.
That means your lap history from before APEX existed is recoverable —
times and sectors only, no telemetry channels, so these laps show up in
the library (and count toward PBs and the ideal lap) but can't be opened
in trace analysis.

Idempotent: each session is keyed by filename+section, so re-running only
imports what's new.
"""

from __future__ import annotations

import json
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..schema import LapResult, SessionContext
from ..storage import LapStore

logger = logging.getLogger(__name__)

_LMU_CANDIDATES = [
    Path(r"C:\Program Files (x86)\Steam\steamapps\common\Le Mans Ultimate"),
    Path(r"C:\SteamLibrary\steamapps\common\Le Mans Ultimate"),
    Path(r"D:\SteamLibrary\steamapps\common\Le Mans Ultimate"),
]

_SESSION_TAGS = re.compile(r"^(Practice\d?|Qualify\d?|Warmup|Race\d?)$")


def find_lmu() -> Optional[Path]:
    for c in _LMU_CANDIDATES:
        if c.exists():
            return c
    return None


def player_name(lmu: Path) -> str:
    try:
        settings = json.loads(
            (lmu / "UserData" / "player" / "Settings.JSON").read_text(
                encoding="utf-8", errors="replace"))
        for section in settings.values():
            if isinstance(section, dict) and "Player Name" in section:
                return section["Player Name"]
    except Exception:
        pass
    return ""


def _parse_xml(path: Path) -> Optional[ET.Element]:
    raw = path.read_bytes()
    # header claims utf-8 but the engine actually writes Latin-1 accents
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1", errors="replace")
    # internal DTD entity (&rFEnt;) breaks ElementTree — inline and drop it
    text = re.sub(r"<!DOCTYPE[^]]*\]>", "", text, flags=re.S)
    text = text.replace("&rFEnt;", "rFactor Entity")
    try:
        return ET.fromstring(text)
    except ET.ParseError as e:
        logger.warning("results: cannot parse %s: %s", path.name, e)
        return None


def _session_type(tag: str) -> str:
    t = tag.lower()
    if t.startswith("practice"):
        return "practice"
    if t.startswith("qualify"):
        return "qualifying"
    if t.startswith("warmup"):
        return "warmup"
    return "race"


def import_results(store: LapStore, lmu_root: Optional[Path] = None) -> dict:
    """Scan the results folder and import the player's laps. Returns counts."""
    lmu = lmu_root or find_lmu()
    if lmu is None:
        return {"error": "LMU install not found", "sessions": 0, "laps": 0}
    results_dir = lmu / "UserData" / "Log" / "Results"
    if not results_dir.exists():
        return {"error": "no Results folder", "sessions": 0, "laps": 0}
    me = player_name(lmu)

    existing = store.existing_import_keys()
    # Laps recorded live must not reappear as history duplicates: the game
    # logs the same session we captured with full telemetry. Key by
    # (track, car, rounded lap time).
    live = {
        (l["track"], l["car"], round(l["lap_time"], 3))
        for l in store.list_laps()
        if l["source"] == "recorded"
    }
    new_sessions = 0
    new_laps = 0

    for xml_path in sorted(results_dir.glob("*.xml")):
        root = _parse_xml(xml_path)
        if root is None:
            continue
        race = root.find("RaceResults")
        if race is None:
            continue
        # TrackCourse is the layout actually driven (e.g. "Sebring School
        # Circuit"); TrackVenue is just the facility. Mixing layouts would
        # blend their lap times, PBs, and ideal laps.
        track = (race.findtext("TrackCourse") or race.findtext("TrackVenue") or "").strip()
        when_str = (race.findtext("TimeString") or "").strip()
        try:
            started = datetime.strptime(when_str, "%Y/%m/%d %H:%M:%S").isoformat()
        except ValueError:
            started = when_str

        for section in race:
            if not _SESSION_TAGS.match(section.tag):
                continue
            key = f"{xml_path.name}:{section.tag}"
            if key in existing:
                continue

            laps_to_add = []
            car = ""
            car_class = ""
            for drv in section.iter("Driver"):
                name = (drv.findtext("Name") or "").strip()
                is_player = (drv.findtext("isPlayer") or "0").strip() == "1"
                if not is_player or (me and name != me):
                    continue
                car = (drv.findtext("VehName") or "").strip()
                car_class = (drv.findtext("CarClass") or "").strip()
                for lap_el in drv.iter("Lap"):
                    t = (lap_el.text or "").strip()
                    if not t or t.startswith("--"):
                        continue  # uncounted lap (cut, reset, out-lap)
                    try:
                        lap_time = float(t)
                    except ValueError:
                        continue
                    car_now = (drv.findtext("VehName") or "").strip()
                    if (track, car_now, round(lap_time, 3)) in live:
                        continue  # already captured live with full telemetry
                    sectors = []
                    s1 = lap_el.get("s1")
                    s2 = lap_el.get("s2")
                    s3 = lap_el.get("s3")
                    if s1 and s2 and s3:
                        # results XML sectors are already per-sector splits
                        sectors = [float(s1), float(s2), float(s3)]
                    laps_to_add.append((int(lap_el.get("num", 0)), lap_time, sectors))

            if not laps_to_add:
                continue
            ctx = SessionContext(
                game="Le Mans Ultimate", track=track, car=car,
                car_class=car_class, session_type=_session_type(section.tag),
            )
            session_id = store.start_session(
                ctx, started_at=started, source="game-log", import_key=key)
            for num, lap_time, sectors in laps_to_add:
                store.save_lap(
                    LapResult(lap_number=num, lap_time=lap_time,
                              sector_times=sectors, valid=True, context=ctx,
                              channels={}),
                    source="game-log", driver=me or "player",
                    session_id=session_id, created_at=started,
                )
                new_laps += 1
            new_sessions += 1

    logger.info("game-log import: %d sessions, %d laps", new_sessions, new_laps)
    return {"sessions": new_sessions, "laps": new_laps}
