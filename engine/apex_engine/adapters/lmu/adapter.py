"""Le Mans Ultimate adapter.

LMU is built on the rFactor 2 engine and exposes telemetry through the
same shared-memory layout (The Iron Wolf's rF2 Shared Memory Map plugin).
The game must have the plugin DLL enabled — see docs/SETUP_LMU.md.

Reads two buffers:
  Telemetry ($rFactor2SMMP_Telemetry$)  ~50 Hz: pedals, speed, position
  Scoring   ($rFactor2SMMP_Scoring$)    ~5 Hz: lap/sector times, lap distance
"""

from __future__ import annotations

import math
from typing import Optional

from ...schema import TelemetryFrame, SessionContext
from ..base import BaseAdapter
from . import rf2_data
from .rf2_mmap import MMapControl
from .rf2_data import rFactor2Constants as C

_SESSION_TYPES = {0: "test", 1: "practice", 2: "practice", 3: "practice",
                  4: "practice", 5: "qualifying", 6: "qualifying",
                  7: "qualifying", 8: "qualifying", 9: "warmup",
                  10: "race", 11: "race", 12: "race", 13: "race"}


def _decode(raw: bytes) -> str:
    raw = raw.split(b"\x00", 1)[0]
    try:
        return raw.decode("utf-8").strip()
    except UnicodeDecodeError:
        return raw.decode("iso-8859-1", errors="replace").strip()


class LMUAdapter(BaseAdapter):
    name = "lmu"
    game_title = "Le Mans Ultimate"
    rate_hz = 50.0

    def __init__(self):
        self._tele: Optional[MMapControl] = None
        self._scor: Optional[MMapControl] = None
        self._last_version = -1

    # -- BaseAdapter --------------------------------------------------

    def connect(self) -> bool:
        try:
            tele = MMapControl(C.MM_TELEMETRY_FILE_NAME, rf2_data.rF2Telemetry)
            tele.create()
            scor = MMapControl(C.MM_SCORING_FILE_NAME, rf2_data.rF2Scoring)
            scor.create()
        except OSError:
            return False
        self._tele, self._scor = tele, scor
        return True

    def disconnect(self) -> None:
        for m in (self._tele, self._scor):
            if m is not None:
                try:
                    m.close()
                except Exception:
                    pass
        self._tele = self._scor = None

    def is_active(self) -> bool:
        # The mmap exists even before the game writes; a live game keeps
        # bumping the version counter and reports at least one vehicle.
        if self._tele is None:
            return False
        self._tele.update()
        return self._tele.data.mNumVehicles > 0

    def session(self) -> SessionContext:
        if self._scor is None:
            return SessionContext(game=self.game_title)
        self._scor.update()
        info = self._scor.data.mScoringInfo
        player = self._player_scoring()
        return SessionContext(
            game=self.game_title,
            track=_decode(info.mTrackName),
            car=_decode(player.mVehicleName) if player is not None else "",
            track_length=float(info.mLapDist),
            session_type=_SESSION_TYPES.get(int(info.mSession), "unknown"),
        )

    def poll(self) -> Optional[TelemetryFrame]:
        if self._tele is None or self._scor is None:
            return None
        self._tele.update()
        self._scor.update()

        scor_v = self._player_scoring()
        if scor_v is None:
            return None
        tele_v = self._player_telemetry(scor_v.mID)
        if tele_v is None:
            return None

        vel = tele_v.mLocalVel
        speed = math.sqrt(vel.x ** 2 + vel.y ** 2 + vel.z ** 2)
        lap_time = max(float(tele_v.mElapsedTime - tele_v.mLapStartET), 0.0)
        # rF2 sector convention: 0 = sector 3, 1 = sector 1, 2 = sector 2
        sector = {0: 3, 1: 1, 2: 2}.get(int(scor_v.mSector), 1)

        return TelemetryFrame(
            timestamp=float(tele_v.mElapsedTime),
            lap_number=int(tele_v.mLapNumber),
            lap_time=lap_time,
            lap_dist=max(float(scor_v.mLapDist), 0.0),
            pos_x=float(tele_v.mPos.x),
            pos_y=float(tele_v.mPos.y),
            pos_z=float(tele_v.mPos.z),
            speed=speed,
            throttle=float(tele_v.mUnfilteredThrottle),
            brake=float(tele_v.mUnfilteredBrake),
            clutch=float(tele_v.mUnfilteredClutch),
            steering=float(tele_v.mUnfilteredSteering),
            gear=int(tele_v.mGear),
            rpm=float(tele_v.mEngineRPM),
            sector=sector,
            last_lap_time=float(scor_v.mLastLapTime),
            best_lap_time=float(scor_v.mBestLapTime),
            last_s1=float(scor_v.mLastSector1),
            last_s2=float(scor_v.mLastSector2),
            cur_s1=float(scor_v.mCurSector1),
            cur_s2=float(scor_v.mCurSector2),
            in_pits=bool(scor_v.mInPits),
            count_flag=int(scor_v.mCountLapFlag),
        )

    # -- helpers ------------------------------------------------------

    def _player_scoring(self):
        data = self._scor.data
        for i in range(min(data.mScoringInfo.mNumVehicles, C.MAX_MAPPED_VEHICLES)):
            if data.mVehicles[i].mIsPlayer:
                return data.mVehicles[i]
        return None

    def _player_telemetry(self, slot_id: int):
        data = self._tele.data
        for i in range(min(data.mNumVehicles, C.MAX_MAPPED_VEHICLES)):
            if data.mVehicles[i].mID == slot_id:
                return data.mVehicles[i]
        return None
