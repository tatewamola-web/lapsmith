"""Lap storage: SQLite for metadata, .npz files for channel data.

Also implements the .lapsmith interchange format — a zip holding the lap's
metadata (JSON) and channels (npz) — used for sharing reference laps
between drivers. A world-record or coach lap arrives the same way your
friend's lap does: as a file.
"""

from __future__ import annotations

import io
import json
import sqlite3
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np

from .schema import LapResult, SessionContext, LAP_CHANNELS

SCHEMA = """
CREATE TABLE IF NOT EXISTS laps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    game TEXT NOT NULL,
    track TEXT NOT NULL,
    car TEXT NOT NULL,
    session_type TEXT,
    lap_number INTEGER,
    lap_time REAL NOT NULL,
    s1 REAL, s2 REAL, s3 REAL,
    valid INTEGER NOT NULL,
    source TEXT NOT NULL DEFAULT 'recorded',  -- recorded | imported
    driver TEXT NOT NULL DEFAULT 'me'
);
CREATE INDEX IF NOT EXISTS idx_laps_combo ON laps (game, track, car, valid, lap_time);
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    game TEXT NOT NULL,
    track TEXT NOT NULL,
    car TEXT NOT NULL,
    session_type TEXT
);
"""


class LapStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.laps_dir = self.root / "laps"
        self.laps_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "apex.db"
        with self._conn() as con:
            con.executescript(SCHEMA)
            self._migrate(con)

    def _migrate(self, con: sqlite3.Connection) -> None:
        cols = {r["name"] for r in con.execute("PRAGMA table_info(laps)")}
        if "session_id" not in cols:
            con.execute("ALTER TABLE laps ADD COLUMN session_id INTEGER")
        if "car_class" not in cols:
            con.execute("ALTER TABLE laps ADD COLUMN car_class TEXT NOT NULL DEFAULT ''")
        scols = {r["name"] for r in con.execute("PRAGMA table_info(sessions)")}
        if "source" not in scols:
            con.execute("ALTER TABLE sessions ADD COLUMN source TEXT NOT NULL DEFAULT 'live'")
        if "import_key" not in scols:
            con.execute("ALTER TABLE sessions ADD COLUMN import_key TEXT")
        if "car_class" not in scols:
            con.execute("ALTER TABLE sessions ADD COLUMN car_class TEXT NOT NULL DEFAULT ''")
        # Backfill: pre-session laps get one session per game/track/car combo.
        orphans = con.execute(
            "SELECT game, track, car, session_type, MIN(created_at) AS t0"
            " FROM laps WHERE session_id IS NULL GROUP BY game, track, car"
        ).fetchall()
        for o in orphans:
            cur = con.execute(
                "INSERT INTO sessions (started_at, game, track, car, session_type)"
                " VALUES (?,?,?,?,?)",
                (o["t0"], o["game"], o["track"], o["car"], o["session_type"]),
            )
            con.execute(
                "UPDATE laps SET session_id=? WHERE session_id IS NULL"
                " AND game=? AND track=? AND car=?",
                (cur.lastrowid, o["game"], o["track"], o["car"]),
            )

    def start_session(self, ctx: SessionContext, started_at: Optional[str] = None,
                      source: str = "live", import_key: Optional[str] = None) -> int:
        with self._conn() as con:
            cur = con.execute(
                "INSERT INTO sessions (started_at, game, track, car, session_type,"
                " source, import_key, car_class) VALUES (?,?,?,?,?,?,?,?)",
                (started_at or datetime.now(timezone.utc).isoformat(), ctx.game,
                 ctx.track, ctx.car, ctx.session_type, source, import_key,
                 ctx.car_class),
            )
            return cur.lastrowid

    def find_recent_session(self, ctx: SessionContext,
                            max_age_s: float = 3 * 3600) -> Optional[int]:
        """Most recent live session matching this context, if fresh enough —
        so an engine restart mid-stint continues the same session instead of
        fragmenting it."""
        with self._conn() as con:
            row = con.execute(
                "SELECT id, started_at FROM sessions WHERE source='live'"
                " AND game=? AND track=? AND car=? AND session_type=?"
                " ORDER BY id DESC LIMIT 1",
                (ctx.game, ctx.track, ctx.car, ctx.session_type),
            ).fetchone()
        if row is None:
            return None
        try:
            started = datetime.fromisoformat(row["started_at"])
            age = (datetime.now(timezone.utc) - started).total_seconds()
        except ValueError:
            return None
        return row["id"] if age < max_age_s else None

    def existing_import_keys(self) -> set:
        with self._conn() as con:
            rows = con.execute(
                "SELECT import_key FROM sessions WHERE import_key IS NOT NULL"
            ).fetchall()
        return {r["import_key"] for r in rows}

    def ideal_lap(self, game: str, track: str, car_class: str = "",
                  car: str = "") -> Optional[dict]:
        """Theoretical best: fastest recorded time in each sector, combined,
        grouped by class (per car when class unknown)."""
        with self._conn() as con:
            if car_class:
                row = con.execute(
                    "SELECT MIN(s1) AS s1, MIN(s2) AS s2, MIN(s3) AS s3,"
                    " COUNT(*) AS laps_with_sectors FROM laps"
                    " WHERE valid=1 AND source != 'opponent'"
                    " AND game=? AND track=? AND car_class=?"
                    " AND s1 IS NOT NULL AND s2 IS NOT NULL AND s3 IS NOT NULL",
                    (game, track, car_class),
                ).fetchone()
            else:
                row = con.execute(
                    "SELECT MIN(s1) AS s1, MIN(s2) AS s2, MIN(s3) AS s3,"
                    " COUNT(*) AS laps_with_sectors FROM laps"
                    " WHERE valid=1 AND source != 'opponent'"
                    " AND game=? AND track=? AND car=?"
                    " AND s1 IS NOT NULL AND s2 IS NOT NULL AND s3 IS NOT NULL",
                    (game, track, car),
                ).fetchone()
        if row is None or row["s1"] is None:
            return None
        pb = self.personal_best(game, track, car_class=car_class, car=car)
        total = row["s1"] + row["s2"] + row["s3"]
        return {
            "s1": row["s1"], "s2": row["s2"], "s3": row["s3"],
            "total": total,
            "laps_considered": row["laps_with_sectors"],
            "pb_time": pb["lap_time"] if pb else None,
            "gap_to_pb": (pb["lap_time"] - total) if pb else None,
        }

    def list_sessions(self) -> list[dict]:
        """Session list; lap counts and bests are the player's own laps —
        captured opponent laps live in the session but don't inflate it."""
        with self._conn() as con:
            rows = con.execute(
                "SELECT s.*, COUNT(l.id) AS laps, COALESCE(SUM(l.valid), 0) AS valid_laps,"
                " MIN(CASE WHEN l.valid=1 THEN l.lap_time END) AS best_lap"
                " FROM sessions s LEFT JOIN laps l ON l.session_id = s.id"
                "   AND l.source != 'opponent'"
                " GROUP BY s.id HAVING COUNT(l.id) > 0 ORDER BY s.id DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def combo_best(self, game: str, track: str, car_class: str = "",
                   car: str = "") -> Optional[float]:
        """Fastest valid lap time for a combo across ALL sources."""
        with self._conn() as con:
            if car_class:
                row = con.execute(
                    "SELECT MIN(lap_time) AS t FROM laps WHERE valid=1"
                    " AND game=? AND track=? AND car_class=?",
                    (game, track, car_class)).fetchone()
            else:
                row = con.execute(
                    "SELECT MIN(lap_time) AS t FROM laps WHERE valid=1"
                    " AND game=? AND track=? AND car=?",
                    (game, track, car)).fetchone()
        return row["t"] if row and row["t"] is not None else None

    def _conn(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        return con

    # -- write ---------------------------------------------------------

    def save_lap(self, lap: LapResult, source: str = "recorded",
                 driver: str = "me", session_id: Optional[int] = None,
                 created_at: Optional[str] = None) -> int:
        s = lap.sector_times or [None, None, None]
        with self._conn() as con:
            cur = con.execute(
                "INSERT INTO laps (created_at, game, track, car, session_type,"
                " lap_number, lap_time, s1, s2, s3, valid, source, driver,"
                " session_id, car_class)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    created_at or datetime.now(timezone.utc).isoformat(),
                    lap.context.game, lap.context.track, lap.context.car,
                    lap.context.session_type, lap.lap_number, lap.lap_time,
                    s[0], s[1], s[2], int(lap.valid), source, driver, session_id,
                    lap.context.car_class,
                ),
            )
            lap_id = cur.lastrowid
        if lap.channels:  # game-log imports have times only, no channel data
            arrays = {ch: np.asarray(vals, dtype=np.float32)
                      for ch, vals in lap.channels.items()}
            np.savez_compressed(self.laps_dir / f"{lap_id}.npz", **arrays)
        return lap_id

    def delete_lap(self, lap_id: int) -> None:
        with self._conn() as con:
            con.execute("DELETE FROM laps WHERE id=?", (lap_id,))
        (self.laps_dir / f"{lap_id}.npz").unlink(missing_ok=True)

    # -- read ----------------------------------------------------------

    def list_laps(self, track: Optional[str] = None, car: Optional[str] = None,
                  game: Optional[str] = None,
                  session_id: Optional[int] = None) -> list[dict]:
        q = "SELECT * FROM laps WHERE 1=1"
        args: list = []
        for col, val in (("track", track), ("car", car), ("game", game),
                         ("session_id", session_id)):
            if val:
                q += f" AND {col}=?"
                args.append(val)
        q += " ORDER BY created_at DESC, id DESC"
        with self._conn() as con:
            rows = [dict(r) for r in con.execute(q, args)]
        pb = self._pb_ids()
        for r in rows:
            r["is_pb"] = r["id"] in pb
            r["has_data"] = (self.laps_dir / f"{r['id']}.npz").exists()
        return rows

    def get_lap(self, lap_id: int) -> Optional[dict]:
        with self._conn() as con:
            row = con.execute("SELECT * FROM laps WHERE id=?", (lap_id,)).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["is_pb"] = d["id"] in self._pb_ids()
        return d

    def load_channels(self, lap_id: int) -> Optional[dict[str, np.ndarray]]:
        path = self.laps_dir / f"{lap_id}.npz"
        if not path.exists():
            return None
        with np.load(path) as z:
            return {k: z[k] for k in z.files}

    def personal_best(self, game: str, track: str, car_class: str = "",
                      car: str = "") -> Optional[dict]:
        """Fastest valid lap for the class (falls back to per-car when the
        class is unknown, e.g. history rows imported before classes existed)."""
        with self._conn() as con:
            if car_class:
                row = con.execute(
                    "SELECT * FROM laps WHERE game=? AND track=? AND car_class=?"
                    " AND valid=1 AND source != 'opponent'"
                    " ORDER BY lap_time ASC LIMIT 1",
                    (game, track, car_class),
                ).fetchone()
            else:
                row = con.execute(
                    "SELECT * FROM laps WHERE game=? AND track=? AND car=?"
                    " AND valid=1 AND source != 'opponent'"
                    " ORDER BY lap_time ASC LIMIT 1",
                    (game, track, car),
                ).fetchone()
        return dict(row) if row else None

    def _pb_ids(self) -> set[int]:
        """Fastest valid lap id per (game, track, class) — per car when the
        class is blank."""
        with self._conn() as con:
            rows = con.execute(
                "SELECT id FROM laps l WHERE valid=1 AND source != 'opponent'"
                " AND id = ("
                " SELECT id FROM laps WHERE valid=1 AND source != 'opponent'"
                " AND game=l.game AND track=l.track"
                " AND ((l.car_class != '' AND car_class = l.car_class)"
                "   OR (l.car_class = '' AND car = l.car))"
                " ORDER BY lap_time ASC, id ASC LIMIT 1)"
            ).fetchall()
        return {r["id"] for r in rows}

    # -- interchange (.apexlap) -----------------------------------------

    def export_lap(self, lap_id: int) -> Optional[bytes]:
        meta = self.get_lap(lap_id)
        channels = self.load_channels(lap_id)
        if meta is None or channels is None:
            return None
        buf = io.BytesIO()
        npz = io.BytesIO()
        np.savez_compressed(npz, **channels)
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("meta.json", json.dumps(meta, indent=2))
            zf.writestr("channels.npz", npz.getvalue())
        return buf.getvalue()

    def import_lap(self, data: bytes, driver: str = "") -> int:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            meta = json.loads(zf.read("meta.json"))
            with np.load(io.BytesIO(zf.read("channels.npz"))) as z:
                channels = {k: z[k].tolist() for k in z.files}
        lap = LapResult(
            lap_number=meta.get("lap_number", 0),
            lap_time=meta["lap_time"],
            sector_times=[t for t in (meta.get("s1"), meta.get("s2"), meta.get("s3"))
                          if t is not None],
            valid=bool(meta.get("valid", True)),
            context=SessionContext(
                game=meta.get("game", ""), track=meta.get("track", ""),
                car=meta.get("car", ""),
                session_type=meta.get("session_type", ""),
            ),
            channels=channels,
        )
        return self.save_lap(lap, source="imported",
                             driver=driver or meta.get("driver", "imported"))
