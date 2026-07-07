"""FastAPI server: the bridge between the telemetry engine and the UI.

Two surfaces:
  REST  /api/...   lap library, comparisons, import/export
  WS    /ws/live   live normalized frames (~25 Hz) for dashboards/overlays

The engine loop runs in a daemon thread: it connects the adapter,
polls frames at the adapter's rate, and feeds the recorder. The web
layer only ever reads the latest frame snapshot.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from . import analysis
from .adapters import get_adapter
from .recorder import LapRecorder
from .schema import TelemetryFrame, SessionContext
from .storage import LapStore

logger = logging.getLogger(__name__)


class Engine:
    """Owns the adapter loop and the latest-state snapshot."""

    def __init__(self, adapter_name: str, data_dir: Path):
        self.adapter_name = adapter_name
        self.store = LapStore(data_dir)
        self.recorder = LapRecorder(on_lap=self._on_lap)
        self.latest: Optional[TelemetryFrame] = None
        self.session: SessionContext = SessionContext()
        self.session_id: Optional[int] = None
        self.connected = False
        self.laps_recorded = 0
        # One recorder per same-class opponent: their completed laps are
        # captured live from shared memory — real reference laps from
        # faster drivers, full telemetry included.
        self._opponents: dict[int, LapRecorder] = {}
        self._opponent_meta: dict[int, tuple[str, str]] = {}  # id -> (driver, car)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True, name="engine")
        self._thread.start()

    def stop(self):
        self._stop.set()

    def snapshot(self):
        with self._lock:
            return self.latest, self.session, self.connected

    def _on_lap(self, lap):
        # Session rows are created lazily on the first stored lap, so idle
        # engine restarts don't litter the library with empty sessions.
        if self.session_id is None:
            self.session_id = self.store.start_session(lap.context)
            logger.info("session #%d: %s / %s", self.session_id,
                        lap.context.track, lap.context.car)
        # Store every completed lap, even invalid ones (flagged, filtered in UI).
        lap_id = self.store.save_lap(lap, session_id=self.session_id)
        self.laps_recorded += 1
        logger.info("stored lap id=%d time=%.3f valid=%s", lap_id, lap.lap_time, lap.valid)

    def _feed_opponents(self, adapter):
        """Record every same-class car; only laps faster than your PB are
        kept (that's the point — reference laps from quicker drivers)."""
        try:
            others = adapter.poll_all()
        except Exception:
            return
        seen = set()
        for slot_id, driver, car, frame in others:
            seen.add(slot_id)
            rec = self._opponents.get(slot_id)
            if rec is None:
                ctx = SessionContext(
                    game=self.session.game, track=self.session.track,
                    car=car, car_class=self.session.car_class,
                    track_length=self.session.track_length,
                    session_type=self.session.session_type,
                )
                rec = LapRecorder(
                    on_lap=lambda lap, d=driver: self._on_opponent_lap(lap, d))
                rec.set_context(ctx)
                self._opponents[slot_id] = rec
            self._opponent_meta[slot_id] = (driver, car)
            rec.feed(frame)
        # cars that left the session
        for gone in set(self._opponents) - seen:
            self._opponents.pop(gone, None)
            self._opponent_meta.pop(gone, None)

    def _on_opponent_lap(self, lap, driver: str):
        if not lap.valid:
            return
        pb = self.store.personal_best(lap.context.game, lap.context.track,
                                      car_class=lap.context.car_class,
                                      car=lap.context.car)
        # keep only laps that would teach you something
        if pb is not None and lap.lap_time >= pb["lap_time"]:
            return
        lap_id = self.store.save_lap(lap, source="opponent", driver=driver,
                                     session_id=self.session_id)
        logger.info("opponent lap kept: %s %.3f (id=%d)", driver, lap.lap_time, lap_id)

    def _run(self):
        adapter = get_adapter(self.adapter_name)
        interval = 1.0 / adapter.rate_hz
        session_refresh = 0.0
        while not self._stop.is_set():
            if not self.connected:
                if adapter.connect():
                    self.connected = True
                    logger.info("adapter '%s' connected", adapter.name)
                else:
                    time.sleep(2.0)
                    continue
            try:
                if not adapter.is_active():
                    time.sleep(1.0)
                    continue
                now = time.monotonic()
                if now >= session_refresh:
                    ctx = adapter.session()
                    session_refresh = now + 5.0
                    # Track/car change = the next lap belongs to a new session.
                    if ctx.track and (
                        ctx.track != self.session.track
                        or ctx.car != self.session.car
                    ):
                        self.session_id = None
                    with self._lock:
                        self.session = ctx
                    self.recorder.set_context(ctx)
                frame = adapter.poll()
                if frame is not None:
                    self.recorder.feed(frame)
                    with self._lock:
                        self.latest = frame
                self._feed_opponents(adapter)
                time.sleep(interval)
            except Exception:
                logger.exception("engine loop error; reconnecting")
                adapter.disconnect()
                self.connected = False
                time.sleep(2.0)


def create_app(adapter_name: str = "sim", data_dir: Path = Path("data")) -> FastAPI:
    engine = Engine(adapter_name, data_dir)
    app = FastAPI(title="Lapsmith Telemetry Engine")
    app.state.engine = engine

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    def _startup():
        engine.start()
        # Pull historical lap times from the game's own result logs so old
        # PBs exist from the first launch. Idempotent, so safe every start.
        if adapter_name == "lmu":
            def _import():
                try:
                    from .importers.lmu_results import import_results
                    import_results(engine.store)
                except Exception:
                    logger.exception("game-history import failed")
            threading.Thread(target=_import, daemon=True, name="history-import").start()

    @app.on_event("shutdown")
    def _shutdown():
        engine.stop()

    # -- status / live ------------------------------------------------

    @app.get("/api/status")
    def status():
        frame, session, connected = engine.snapshot()
        return {
            "adapter": engine.adapter_name,
            "connected": connected,
            "live": frame is not None,
            "session": session.to_dict(),
            "laps_recorded": engine.laps_recorded,
        }

    @app.websocket("/ws/live")
    async def ws_live(ws: WebSocket):
        await ws.accept()
        last_ts = None
        try:
            while True:
                frame, session, _ = engine.snapshot()
                if frame is not None and frame.timestamp != last_ts:
                    last_ts = frame.timestamp
                    await ws.send_text(json.dumps({
                        "type": "frame",
                        "frame": frame.to_dict(),
                        "session": session.to_dict(),
                    }))
                await asyncio.sleep(0.04)  # ~25 Hz to clients
        except WebSocketDisconnect:
            pass

    # -- lap library ---------------------------------------------------

    @app.get("/api/sessions")
    def sessions():
        return engine.store.list_sessions()

    @app.get("/api/laps")
    def laps(track: Optional[str] = None, car: Optional[str] = None,
             session: Optional[int] = None):
        return engine.store.list_laps(track=track, car=car, session_id=session)

    @app.get("/api/pb")
    def pb(game: str, track: str, car: str = "", car_class: str = ""):
        lap = engine.store.personal_best(game, track, car_class=car_class, car=car)
        return lap if lap else Response(status_code=404)

    @app.get("/api/laps/{lap_id}")
    def lap_meta(lap_id: int):
        lap = engine.store.get_lap(lap_id)
        return lap if lap else Response(status_code=404)

    @app.get("/api/laps/{lap_id}/data")
    def lap_data(lap_id: int):
        channels = engine.store.load_channels(lap_id)
        if channels is None:
            return Response(status_code=404)
        return analysis.lap_channels_payload(channels)

    @app.delete("/api/laps/{lap_id}")
    def lap_delete(lap_id: int):
        engine.store.delete_lap(lap_id)
        return {"ok": True}

    # -- comparison ------------------------------------------------------

    @app.get("/api/compare")
    def compare(lap: int, ref: int):
        a = engine.store.load_channels(lap)
        b = engine.store.load_channels(ref)
        if a is None or b is None:
            return Response(status_code=404)
        payload = analysis.compare(a, b)
        if payload is None:
            return Response(status_code=422)
        payload["lap_meta"] = engine.store.get_lap(lap)
        payload["ref_meta"] = engine.store.get_lap(ref)
        return payload

    @app.get("/api/insights")
    def insights(lap: int, ref: int):
        a = engine.store.load_channels(lap)
        b = engine.store.load_channels(ref)
        ref_meta = engine.store.get_lap(ref)
        if a is None or b is None or ref_meta is None:
            return Response(status_code=404)
        # analysis wants rF2-style cumulative s2 (s1 + s2 splits)
        s1 = ref_meta.get("s1") or -1.0
        s2 = (ref_meta["s1"] + ref_meta["s2"]) if ref_meta.get("s1") and ref_meta.get("s2") else -1.0
        payload = analysis.insights(a, b, ref_s1=s1, ref_s2=s2,
                                    track=ref_meta.get("track", ""))
        if payload is None:
            return Response(status_code=422)
        return payload

    @app.get("/api/ideal")
    def ideal(game: str, track: str, car: str = "", car_class: str = ""):
        result = engine.store.ideal_lap(game, track, car_class=car_class, car=car)
        return result if result else Response(status_code=404)

    @app.post("/api/import/game-history")
    def import_game_history():
        from .importers.lmu_results import import_results
        return import_results(engine.store)

    # -- interchange -----------------------------------------------------

    @app.get("/api/laps/{lap_id}/export")
    def lap_export(lap_id: int):
        data = engine.store.export_lap(lap_id)
        if data is None:
            return Response(status_code=404)
        return Response(
            content=data,
            media_type="application/zip",
            headers={"Content-Disposition":
                     f'attachment; filename="lap_{lap_id}.lapsmith"'},
        )

    @app.post("/api/laps/import")
    async def lap_import(file: UploadFile):
        lap_id = engine.store.import_lap(await file.read())
        return {"id": lap_id}

    # Serve the built UI (ui/dist) when present, so the whole app runs as
    # one process at http://localhost:8000 with no dev tooling.
    dist = Path(__file__).resolve().parents[2] / "ui" / "dist"
    if dist.exists():
        from fastapi.staticfiles import StaticFiles
        app.mount("/", StaticFiles(directory=dist, html=True), name="ui")

    return app
