# APEX — Sim Racing Telemetry Analysis

A desktop telemetry platform for sim racing: record every lap you drive,
compare laps corner-by-corner against faster reference laps, and see exactly
where the time is lost.

Built to support many sims through one adapter architecture. First supported
game: **Le Mans Ultimate**. Designed-for next: iRacing, ACC, Assetto Corsa.

## How it works

```
┌─────────────┐   normalized    ┌──────────────┐   REST + WebSocket   ┌─────────┐
│ Game adapter │ ──── frames ──▶ │ Engine        │ ──────────────────▶ │ UI       │
│ (LMU, sim,   │    (50 Hz)      │  · recorder   │                     │ analysis │
│  iracing...) │                 │  · lap store  │                     │ overlays │
└─────────────┘                 │  · analysis   │                     └─────────┘
                                └──────────────┘
```

- **Adapters** translate each sim's raw telemetry into one normalized format
  (`engine/apex_engine/adapters/`). Adding a game = writing one adapter.
- **Recorder** watches the stream and cuts it into laps, with validity rules
  (full track coverage, no pit visits).
- **Storage** keeps lap metadata in SQLite and channel data in compressed
  arrays. Personal bests are tracked per game + track + car.
- **Analysis** compares laps *by track position, not by time* — so corners
  line up — and computes the time-delta curve between any two laps.
- **Reference laps travel as `.apexlap` files** — export yours, import a
  faster friend's, same mechanism a coach or world-record lap would use.
- **UI** is a dark, data-dense analysis screen: delta graph, speed/pedal/
  steering traces with synced cursors, and a track map colored by where you
  gain or lose time.

## Quick start

```powershell
./scripts/apex.ps1              # one click: engine + UI at http://localhost:8000
./scripts/apex.ps1 -Adapter sim # demo mode, no game needed
```

The engine serves the built UI itself — no dev tools or other programs
required. For UI development with hot reload:

```powershell
./scripts/dev.ps1        # engine with simulated driver + Vite dev server (:5173)
```

The simulated adapter drives realistic, imperfect laps around a synthetic
circuit so the whole app can be developed and demoed without a sim running.

## With Le Mans Ultimate

See [docs/SETUP_LMU.md](docs/SETUP_LMU.md). Short version: enable plugins in
LMU's gameplay settings, then:

```powershell
./scripts/lmu.ps1
```

## Project layout

```
engine/   Python telemetry engine (FastAPI, numpy)
ui/       React + Vite analysis UI (uPlot charts)
docs/     per-sim setup guides
scripts/  one-command launchers
```
