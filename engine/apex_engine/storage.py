"""Lap storage: SQLite for metadata, .npz files for channel data.

Also implements the .apexlap interchange format — a zip holding the lap's
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
"""


class LapStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.laps_dir = self.root / "laps"
        self.laps_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "apex.db"
        with self._conn() as con:
            con.executescript(SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        return con

    # -- write ---------------------------------------------------------

    def save_lap(self, lap: LapResult, source: str = "recorded",
                 driver: str = "me") -> int:
        s = lap.sector_times or [None, None, None]
        with self._conn() as con:
            cur = con.execute(
                "INSERT INTO laps (created_at, game, track, car, session_type,"
                " lap_number, lap_time, s1, s2, s3, valid, source, driver)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    datetime.now(timezone.utc).isoformat(),
                    lap.context.game, lap.context.track, lap.context.car,
                    lap.context.session_type, lap.lap_number, lap.lap_time,
                    s[0], s[1], s[2], int(lap.valid), source, driver,
                ),
            )
            lap_id = cur.lastrowid
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
                  game: Optional[str] = None) -> list[dict]:
        q = "SELECT * FROM laps WHERE 1=1"
        args: list = []
        for col, val in (("track", track), ("car", car), ("game", game)):
            if val:
                q += f" AND {col}=?"
                args.append(val)
        q += " ORDER BY id DESC"
        with self._conn() as con:
            rows = [dict(r) for r in con.execute(q, args)]
        pb = self._pb_ids()
        for r in rows:
            r["is_pb"] = r["id"] in pb
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

    def personal_best(self, game: str, track: str, car: str) -> Optional[dict]:
        with self._conn() as con:
            row = con.execute(
                "SELECT * FROM laps WHERE game=? AND track=? AND car=? AND valid=1"
                " ORDER BY lap_time ASC LIMIT 1",
                (game, track, car),
            ).fetchone()
        return dict(row) if row else None

    def _pb_ids(self) -> set[int]:
        """Fastest valid lap id per (game, track, car) combo."""
        with self._conn() as con:
            rows = con.execute(
                "SELECT id FROM laps l WHERE valid=1 AND lap_time = ("
                " SELECT MIN(lap_time) FROM laps"
                " WHERE valid=1 AND game=l.game AND track=l.track AND car=l.car)"
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
