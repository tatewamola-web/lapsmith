# Le Mans Ultimate setup

LMU (rFactor 2 engine) exposes telemetry through shared memory. On current
Windows builds this is **built into the game** — no third-party plugin needed.

## Steps

1. Launch LMU.
2. **Settings → Gameplay → Enable Plugins: ON**.
3. Restart LMU if you changed the setting.
4. Start the engine: `./scripts/lapsmith.ps1` (or `engine\.venv\Scripts\python -m apex_engine --adapter lmu`).
5. Open http://localhost:5173 and enter a session in game. The header dot
   turns green (LIVE) once frames arrive; laps appear as you complete them.

## If no data arrives

Older LMU builds may need the community shared-memory plugin:

1. Download `rFactor2SharedMemoryMapPlugin64.dll` from
   https://github.com/TheIronWolfModding/rF2SharedMemoryMapPlugin (releases).
2. Copy it into `<LMU install>\Plugins\`.
3. In `<LMU>\UserData\player\CustomPluginVariables.JSON`, set the plugin's
   `" Enabled"` value to `1`.
4. Restart LMU.

## What the adapter reads

| Buffer | Map name | Rate | Used for |
| ------ | -------- | ---- | -------- |
| Telemetry | `$rFactor2SMMP_Telemetry$` | ~50 Hz | pedals, speed, position, gear, rpm |
| Scoring | `$rFactor2SMMP_Scoring$` | ~5 Hz | lap distance, sector/lap times, pit status |

Lap and sector times always come from the game's own scoring (authoritative),
never from our own clock.
