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
import threading
import time
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
    poll_hz = 200.0  # LMU publishes at 50 Hz; check 4x per frame, act once

    def __init__(self):
        self._tele: Optional[MMapControl] = None
        self._scor: Optional[MMapControl] = None
        self._last_version = -1
        # previous per-wheel brake pressures by slot id, for ABS detection
        self._prev_bp: dict = {}
        # last smoothed lap distance by slot id (kept monotonic within a lap)
        self._prev_dist: dict = {}
        # LMU's local REST API (port 6397) carries what its own HUD shows —
        # per-corner suspension damage, body damage, virtual energy — none of
        # which is in the rF2 shared memory. Polled on a background thread so
        # an HTTP hiccup can never stall the telemetry loop.
        self._rest: dict = {}
        threading.Thread(target=self._poll_rest, daemon=True, name="lmu-rest").start()

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
            car_class=_decode(player.mVehicleClass) if player is not None else "",
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
        return self._build_frame(tele_v, scor_v)

    def _smooth_dist(self, tele_v, scor_v, speed: float) -> float:
        """Lap distance at telemetry rate.

        LMU publishes lap distance in the scoring buffer, which updates only
        ~5x per second: 90% of 50 Hz frames repeated a stale value and then
        jumped ~9 m. That made the live delta saw back and forth, the input
        trace skip, and recorded laps lose resolution. The scoring snapshot
        is stamped with the time it describes (mCurrentET), so advance it by
        speed x (now - then) to get the distance for THIS frame.
        """
        raw = max(float(scor_v.mLapDist), 0.0)
        age = float(tele_v.mElapsedTime) - float(self._scor.data.mScoringInfo.mCurrentET)
        est = raw + speed * min(max(age, 0.0), 0.5)
        key = int(tele_v.mID)
        prev = self._prev_dist.get(key)
        lap = int(tele_v.mLapNumber)
        # never run backwards within a lap (a fresh scoring sample can land
        # slightly behind the extrapolation); a new lap resets it
        if prev is not None and prev[0] == lap and est < prev[1] and prev[1] - est < 30:
            est = prev[1]
        self._prev_dist[key] = (lap, est)
        return est

    def _build_frame(self, tele_v, scor_v) -> TelemetryFrame:
        # ABS detection: pedal held but wheel brake pressures fluttering —
        # that flutter IS the ABS modulating.
        brake_in = float(tele_v.mUnfilteredBrake)
        bp = [float(tele_v.mWheels[i].mBrakePressure) for i in range(4)]
        prev = self._prev_bp.get(int(tele_v.mID))
        abs_active = 0.0
        if prev is not None and brake_in > 0.5:
            flutter = max(abs(bp[i] - prev[i]) for i in range(4))
            if flutter > 0.08:
                abs_active = 1.0
        self._prev_bp[int(tele_v.mID)] = bp

        vel = tele_v.mLocalVel
        speed = math.sqrt(vel.x ** 2 + vel.y ** 2 + vel.z ** 2)
        lap_time = max(float(tele_v.mElapsedTime - tele_v.mLapStartET), 0.0)
        # rF2 sector convention: 0 = sector 3, 1 = sector 1, 2 = sector 2
        sector = {0: 3, 1: 1, 2: 2}.get(int(scor_v.mSector), 1)

        return TelemetryFrame(
            timestamp=float(tele_v.mElapsedTime),
            lap_number=int(tele_v.mLapNumber),
            lap_time=lap_time,
            lap_dist=self._smooth_dist(tele_v, scor_v, speed),
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
            path_lateral=float(scor_v.mPathLateral),
            track_edge=float(scor_v.mTrackEdge),
            abs_active=abs_active,
        )

    def poll_all(self):
        """Frames for every other car in the player's class — the raw feed
        for capturing faster drivers' laps live. Returns
        [(slot_id, driver, car, frame)]. Remote/AI inputs come from the
        same shared memory the game uses to render them."""
        if self._tele is None or self._scor is None:
            return []
        player = self._player_scoring()
        if player is None:
            return []
        my_class = bytes(player.mVehicleClass)
        data = self._scor.data
        tele_by_id = {}
        tdata = self._tele.data
        for i in range(min(tdata.mNumVehicles, C.MAX_MAPPED_VEHICLES)):
            tele_by_id[tdata.mVehicles[i].mID] = tdata.mVehicles[i]
        out = []
        for i in range(min(data.mScoringInfo.mNumVehicles, C.MAX_MAPPED_VEHICLES)):
            sv = data.mVehicles[i]
            if sv.mIsPlayer or bytes(sv.mVehicleClass) != my_class:
                continue
            tv = tele_by_id.get(sv.mID)
            if tv is None:
                continue
            frame = self._build_frame(tv, sv)
            out.append((int(sv.mID), _decode(sv.mDriverName), _decode(sv.mVehicleName), frame))
        return out

    def _poll_rest(self) -> None:
        import json
        import urllib.request
        # 127.0.0.1, not "localhost": Windows tries IPv6 (::1) first, LMU only
        # listens on IPv4, and Python waits ~2 s before falling back.
        base = "http://127.0.0.1:6397"
        n = 0
        while True:
            try:
                cond = json.load(urllib.request.urlopen(
                    base + "/rest/garage/getVehicleCondition", timeout=1))
                update = {
                    "suspension": [float(x) for x in cond.get("suspensionDamage", [0] * 4)],
                    "body": float(cond.get("vehicleDamage", 0.0)),
                }
                if n % 2 == 0:  # parts lost (red on LMU's damage screen)
                    rr = json.load(urllib.request.urlopen(
                        base + "/rest/garage/UIScreen/RepairAndRefuel", timeout=2))
                    parts = rr.get("wearables", {}).get("body", {}).get("detachableParts", [])
                    update["parts_lost"] = sum(1 for x in parts if x)
                if n % 4 == 0:  # energy changes slowly: 0.5 Hz is plenty
                    fuel = json.load(urllib.request.urlopen(
                        base + "/rest/garage/UIScreen/RepairAndRefuel", timeout=2)).get("fuelInfo", {})
                    update["energy"] = float(fuel.get("currentVirtualEnergy", 0.0))
                    update["energy_max"] = float(fuel.get("maxVirtualEnergy", 0.0))
                self._rest = {**self._rest, **update, "at": time.monotonic()}
            except Exception:
                pass  # game not running / API unavailable: just no REST data
            n += 1
            time.sleep(0.5)

    def car_status(self):
        """Health of the player's car for the engineer voice: fuel, tyres,
        damage. Wheel order is FL, FR, RL, RR (rF2 convention)."""
        if self._tele is None or self._scor is None:
            return None
        player = self._player_scoring()
        if player is None:
            return None
        v = self._player_telemetry(player.mID)
        if v is None:
            return None
        return {
            "fuel": float(v.mFuel),
            "fuel_capacity": float(v.mFuelCapacity),
            "flat": [bool(v.mWheels[i].mFlat) for i in range(4)],
            "wheel_detached": [bool(v.mWheels[i].mDetached) for i in range(4)],
            "pressure": [float(v.mWheels[i].mPressure) for i in range(4)],
            "parts_detached": bool(v.mDetached),
            "dents": sum(int(d) for d in v.mDentSeverity),
            # 8 zones around the car, 0/1/2 = LMU's none/yellow/orange
            "dent_zones": [int(d) for d in v.mDentSeverity],
            "impact": float(v.mLastImpactMagnitude),
            "overheating": bool(v.mOverheating),
            "rpm": float(v.mEngineRPM),
            # from LMU's REST API (None until it answers; stale after 3 s = unknown)
            **({k: self._rest[k] for k in ("suspension", "body", "energy", "energy_max", "parts_lost")
                if k in self._rest}
               if time.monotonic() - self._rest.get("at", -1e9) < 3 else {}),
        }

    def nearby(self, radius: float = 25.0):
        """World x/z of the player and every car within `radius` meters
        (cars in the pits excluded) — the spotter's raw input. Reuses the
        buffers poll() just refreshed, so it costs no extra shared-memory read."""
        if self._tele is None or self._scor is None:
            return None
        player = self._player_scoring()
        if player is None:
            return None
        in_pits = {}
        sdata = self._scor.data
        for i in range(min(sdata.mScoringInfo.mNumVehicles, C.MAX_MAPPED_VEHICLES)):
            in_pits[int(sdata.mVehicles[i].mID)] = bool(sdata.mVehicles[i].mInPits)
        me = None
        others = []
        tdata = self._tele.data
        for i in range(min(tdata.mNumVehicles, C.MAX_MAPPED_VEHICLES)):
            v = tdata.mVehicles[i]
            pos = (float(v.mPos.x), float(v.mPos.z))
            if v.mID == player.mID:
                me = pos
            elif not in_pits.get(int(v.mID), False):
                others.append(pos)
        if me is None:
            return None
        r2 = radius * radius
        return me, [o for o in others if (o[0] - me[0]) ** 2 + (o[1] - me[1]) ** 2 < r2]

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
