# Lapsmith Development Log

*(The app was called APEX for its first three days — entries below keep
that name where it was true at the time. Renamed to **Lapsmith** on
2026-07-06 when publishing to GitHub: a smith forges things by hand,
iteratively. That's what this app helps you do to laps.)*

A running record of problems, solutions, and design choices — written to be
mined for essays later. Each entry: what happened, what we did, and why it
matters beyond this project.

---

## 2026-07-04 — Day 1: From idea to working app

### Design choice: adapter architecture
Every sim speaks a different "language" (iRacing shared memory ≠ LMU shared
memory ≠ ACC's UDP). Instead of writing one app per game, the engine defines
a single normalized telemetry format (speed in m/s, pedals 0–1, distance in
meters) and a tiny `BaseAdapter` interface. Each game gets one adapter that
translates its raw data into the normalized form; everything downstream
(recording, storage, analysis, UI) is sim-agnostic.
**Why it matters:** adding a new game means writing one adapter, not
rewriting the app. This is the classic "abstraction boundary" idea — decide
what varies, wall it off behind an interface.

### Design choice: Python engine + web UI
Python for the telemetry engine (proven shared-memory libraries exist for
every target sim; numpy for the math) and React/TypeScript for the UI
(full control over a modern, motorsport-style design). They talk over a
local WebSocket + REST API.
**Why it matters:** each half uses the tool that's best at its job, and the
API boundary between them means either can be replaced without touching the
other.

### Design choice: a simulated driver, because you can't debug at 300 km/h
Built a `SimAdapter` before touching the real game: a small physics model
(corner speed = √(grip × radius), braking/acceleration envelopes, per-lap
random variation) that drives realistic, imperfect laps around a synthetic
circuit. The entire pipeline was built and tested against it headlessly.
**Why it matters:** test infrastructure is a feature. The whole app was
provably working before the first real-game test — so when live testing
failed, we knew the bug was in the adapter layer, not everywhere.

### Design choice: compare laps by track position, not by time
Two laps are compared by asking "at each meter of track, how long did each
lap take to get there?" — delta(d) = t_lap(d) − t_ref(d). Corners line up
regardless of pace; where the delta curve climbs, you're losing time.
**Why it matters:** this is how professional motorsport telemetry works
(MoTeC, Atlas), and it turned a vague goal ("help me get faster") into a
precise mathematical object.

### Design choice: reference laps travel as files
A `.apexlap` file (zip of metadata JSON + compressed channel arrays) can be
exported and imported. Your own PB is tracked automatically; a faster
friend's lap — or someday a pro's — arrives through the same door.
**Why it matters:** designing the general mechanism (file import) instead of
the specific feature (world-record downloads) made the hard version cheap
and the easy version immediate.

### Verified
Smoke test: 6 simulated laps recorded, PB flagged, delta curve's final value
matched the lap-time gap to 2 ms, export/import round-trip clean. UI
rendered live data and comparisons.

---

## 2026-07-05 — Day 2: First contact with the real game

The LMU adapter connected on the first try — then live data found four bugs
that no amount of simulation would have caught. That's the point of testing
against reality.

### Bug 1: Track names showed "AutÃ³dromo" instead of "Autódromo"
LMU writes strings as UTF-8; the adapter decoded them as Latin-1 (the old
rFactor 2 convention). Classic encoding mismatch.
**Fix:** try UTF-8 first, fall back to Latin-1.
**Lesson:** never trust inherited assumptions about text encoding.

### Bug 2: Real laps rendered as flat lines in the charts
The game publishes telemetry at ~50 Hz but lap-distance (scoring) at only
~5 Hz. On the first frames after crossing the line, the distance field still
held the previous lap's value (~5,769 m). The analysis filter, which requires
distance to increase monotonically, saw that stale value first and silently
discarded almost the entire lap.
**Fix:** trim leading samples down to the minimum distance seen in the first
two seconds before applying the monotonic filter.
**Lesson:** when two data streams update at different rates, the moment you
combine them is where bugs live. Silent data loss is the worst kind — the
chart didn't error, it just lied.

### Bug 3: A lap was stored with the previous lap's time
Lap 4 took ~109 s (it included a 7-second off-track moment after the Lesmos
— which the delta curve pinpointed to the meter, at ~2,740 m). But it was
stored as 102.03 s: at the instant the car crossed the line, the slow
scoring feed still reported the *previous* lap's time, and the recorder
trusted it. The comparison math was right; the metadata was the lie.
**Fix:** a finished lap is now "parked" for ~0.6 s until scoring refreshes,
then finalized with the official time — plus a sanity check against our own
elapsed clock.
**Lesson:** a textbook race condition, found not by a crash but by two
numbers disagreeing by exactly one plausible amount. Trust, but verify,
authoritative sources that update asynchronously.

### Bug 4: Cut laps became personal bests
A "1:18.7 PB" at Monza in an LMDh is physically impossible — the final
sector read 10.9 s (real: ~33 s). Track cuts and car resets produce fast
garbage laps, and the app was crowning them.
**Fix:** LMU itself judges every lap via `countLapFlag` (2 = count lap and
time; less = cut/reset). The recorder now watches the flag all lap; a
sustained drop marks the lap invalid. It's still recorded — crash data is
useful — it just can't become a reference. Verified the flag's behavior by
probing shared memory live before wiring it in.
**Lesson:** validate data legitimacy, not just data format. And when the
system of record already has a verdict, use it instead of inventing
heuristics.

### End of day 2
Real Monza laps in the library with correct times and sectors (PB 1:40.329),
verified 50 Hz channel data (gears, pedals, 310 km/h trap speed), and a
delta comparison that located a real driving mistake to within a few meters.

---

## 2026-07-05 — Day 2 (later): The UI grows up

### Feature: sessions, like real telemetry tools
Laps are now grouped into sessions (one per sitting/track/car, like SimHub
or LMU's replay list). A `sessions` table joins to laps; existing laps were
migrated with a backfill that groups them by track/car combo.
**Why it matters:** first schema migration of the project — changing a live
database without losing data is a rite of passage.

### Redesign: tabs (Live / Analysis / Sessions), menu, responsive layout
The single screen became three areas. The live view draws the racing line
(from your PB lap's position data) with a real-time car dot and trail fed
by the WebSocket. Charts switched from kilometers to % of lap on the x-axis
— corners land in the same place visually regardless of track length. The
sidebar no longer clips off-screen: fluid grid columns with sensible
minimums, and the layout collapses to one column under 860 px.

### Design choice: the engine serves the UI — no dev tools to run the app
`npm run build` produces static files; the Python engine serves them at
http://localhost:8000. One process, one URL, one double-click script
(`scripts/apex.ps1`). The app has no dependency on any AI tooling or dev
servers — those were only ever the workbench, not the product.
**Why it matters:** "works on my machine with 3 terminals open" is not
shipping. Collapsing the run story to one click is what makes it shareable.

---

## 2026-07-05 — Day 2 (evening): The app learns to coach

### Feature: automatic corner detection and per-corner coaching
The insights engine finds corners on the *reference* lap by looking for
prominent local minima in smoothed speed (a corner is, mathematically, a
place where you slow down and speed back up). For each corner it measures:
time lost across it (from the delta curve), braking point (first distance
where brake > 40%), apex speed, and throttle-application point — for both
laps — then generates plain-language advice: "carrying 11 km/h less at the
apex; back to full throttle 16m later." Sector boundaries are located by
asking where the reference lap's clock hit its official sector splits.
First real output (Monza, lap 10 vs PB): 6 corners, 2.86s flagged
recoverable, worst at the Roggia chicane and Parabolica.
**Why it matters:** this is the step from *showing* data to *interpreting*
it — the difference between a chart and a coach. All from signal processing
on two arrays; no ML required.

### Bug: the track map was mirrored
Monza looked "backwards." Cause: screen coordinates grow downward while the
game's world z-axis grows in the opposite direction, so every map was a
mirror image. One line (flip z when projecting) fixed both maps.
**Lesson:** coordinate-system handedness is the oldest graphics bug there
is, and it still gets everyone once.

### QoL from user feedback
Unmissable engine state in the header (ENGINE OFFLINE / WAITING FOR GAME /
● RECORDING with pulse), lap list redesigned as two-line rows so nothing
hides behind a horizontal scrollbar, chart zoom documented (drag to zoom,
double-click to reset).

### Honest answer of the day
"Can you see my sessions from before the app existed?" No — and neither
can SimHub: tools only "see everything" that they were running to record.
Telemetry not captured at the moment it happened is gone. That's why the
recording indicator got promoted to the loudest element in the header.

---

## 2026-07-05 — Day 2 (night): History, geometry, and the ideal lap

### Feature: your entire LMU history, recovered
The rF2 engine writes a results XML after every session
(UserData/Log/Results) with every lap and sector time. An importer now
parses those into the library: **59 sessions back to April 24** — Le Mans
race weekends, Spa, Bahrain, Sebring, Imola — times and sectors only
(telemetry channels can't be recovered; nothing recorded them), so they're
marked LOG: they count toward PBs and the ideal lap but can't be charted.
Two encoding traps: the XMLs claim UTF-8 but write Latin-1 accents, and
laps we recorded live had to be deduplicated against their game-log twins —
laps recorded by the *current* engine matched the game's own log to the
millisecond, which is its own little validation.

### Upgrade: corners from track geometry, with real names
Corner detection moved from "where does speed dip" to path curvature —
κ = |x′z″ − z′x″| / (x′² + z′²)^1.5 on the driven line — which finds every
real corner including flat-out ones (Curva Grande never slows the car; only
geometry sees it). A small calibrated database maps detected corners to
their real names: the analysis table now says "T4-5 Variante della Roggia"
instead of "T3". Two tuning lessons: smoothing windows create phantom
curvature at the lap's start/finish (edge artifacts — excluded), and the
grip threshold decides whether Curva Grande is a corner or a straight.

### Feature: theoretical ideal lap
Best S1 + best S2 + best S3 across every lap with sector data (history
included) = the lap you've already proven you can drive, one sector at a
time. Shown next to the real PB with the gap labeled "in your hands."

### UI: markers everywhere, scroll zoom
Sector boundaries (dashed lines) and corner numbers now annotate the delta
and speed charts; T-labels sit on the track map at each apex. Mouse wheel
zooms the charts around the cursor; double-click still resets.

---

## 2026-07-05 — Day 2 (late): Racing lines and organization

### Feature: racing-line comparison with per-corner zoom
The compare payload now carries both laps' world positions, and a new
Racing Line panel overlays them top-down — your line in cyan, the
reference in orange. Corner chips (using official turn numbers: T1-2,
T4-5, T8-9-10, T11) zoom to apex ± 250 m with a direction arrow, which is
where line differences actually become visible.

### Clarified: detected corners vs. official turn numbers
Monza has 11 official turns but 7 braking/cornering *zones* — a chicane is
two turns, one zone. Labels now carry the official numbers so both views
agree with the real track map.

### Organization from user feedback
The all-laps list was chaos once 224 history laps arrived. Now: the
analysis list defaults to the current track + car combo (dropdown for any
other combo, or all laps), and the Sessions tab groups by track with each
track's all-time best, last-driven date, and color-coded session types.
Sessions are created lazily on the first completed lap, so engine restarts
no longer scatter empty session rows.

---

## 2026-07-06 — Day 3: Ghost playback

### Feature: watch laps race each other
The racing-line view gained a play button. Both laps replay **on a shared
clock** — at every instant you see where each car is on the circuit, with
live speed readouts and the running time gap. That's the "ghost car"
concept from racing games, reconstructed from stored telemetry: each lap's
time-over-distance curve is inverted (binary search) to answer "where was
this car at t = 43.2 s?". Scrubber, 0.5–4× speed, and a solo mode for
watching a single lap when no reference is picked.

### Feature: track corridor (approximate track limits)
LMU exposes the distance from the track's center path to its edge
(mTrackEdge), which new laps now record. The line view strokes the
reference path at that width — a gray corridor that makes it obvious when
a line runs wide. Old laps fall back to a constant ~11 m band. Honest
caveat: it's the width at the driven line, not surveyed edge geometry.

### Polish from user feedback (inspiration: Trophi.ai-class tools)
Racing lines thinned to 1.4 px with wheel-zoom + drag-pan; percent labels
dropped from chart axes (sector lines and corner markers are the real
landmarks); throttle/brake and steering charts got the same markers;
session groups are collapsible.

---

## 2026-07-06 — Day 3 (later): Published, then humbled by Sebring

### Shipped: github.com/tatewamola-web/lapsmith
Renamed APEX → **Lapsmith** (a smith forges laps), MIT licensed, public.

### Bug: quitting a session mid-lap forged a personal best
Two Sebring "PBs" (62.4 s, 60.0 s) were laps that never finished: quitting
to the garage resets the sim's lap counter, which the recorder read as a
lap completion — and the abandoned lap's short final sector made it "fast."
**Fix, two layers:** only a clean +1 lap-number increment counts as a
completed lap (resets discard the partial), and a lap is only valid if the
sim published its official time — no official time, no PB, ever.
**Lesson:** never infer an event from a side effect (counter changed) when
the authoritative signal (official lap time issued) exists.

### Bug: the smoothing function was quietly corrupting lap edges
`convolve(mode="same")` zero-pads, so smoothed speed at the start/finish
line sagged toward zero (270 → 192 km/h) and smoothed coordinates bent
toward the origin — faking a braking zone and a kink right at the line.
Every consumer of smoothed data inherited the lie. **Fix:** edge-replicate
padding in one place; phantom corners at 0%/100% vanished on every track.
**Lesson:** library defaults have opinions. Know what your padding does.

### Corner detection, calibrated against Sebring School Circuit
User report: corner count wrong. Three upgrades, verified on real laps:
wrap-around differentiation (closed circuits have no "ends"), splitting
curved regions at distinct curvature peaks (Ascari is three corners, not
one blob), and one-anchor-one-corner naming. Monza now resolves all 11
official turns across 9 zones; Sebring School shows its 7 real corners.

---

## 2026-07-09 → 07-16 — Week 2: Classes, rivals, overlays, real roads

*(Catch-up entry — these shipped across several sessions.)*

### Class-based everything
PBs, the ideal lap, and filtering now group by car class (Hyper, GT3,
LMP3…) read live from shared memory and from the game's result logs —
comparing a Hypercar lap to a GT3 lap was never a fair fight. Existing
laps backfilled by mapping car names to classes from the logs.

### Capturing faster drivers, live
The same shared memory that carries your car carries every car. The
engine now records all same-class opponents during a session and keeps
two kinds of reference laps: any lap faster than everything in the
library, and the best lap of the fastest driver you actually raced.
First online race (Algarve) promptly flooded the library — a dozen
humans improving simultaneously beat the in-memory keep-logic — so the
rule moved into SQL as an idempotent prune the database enforces after
every save. **Lesson: invariants belong in the data layer, not in
whoever remembered to update a variable.**

### In-game overlay (v1 → v2)
A transparent, always-on-top Electron window over the game: a rolling
~800 m trace of the reference lap's throttle/brake with your live inputs
drawn on top, your pedal bars, and a gear digit with the revs wrapped
around it as a ring. Movable, corner-resize scales everything (30%–250%),
stacked or lengthwise layout, auto-hides in menus (the engine only
streams frames while the sim is live — silence *is* the menu detector).
Launched from the app's menu via a one-endpoint spawn.

### Empirical track edges
Sims don't publish surveyed track boundaries, so Lapsmith builds them
from evidence: every valid lap is a sample of legal road; project each
onto the reference line's normals and the min/max envelope (plus half a
car width) traces the road actually used. Every session sharpens the
outline. Off-track laps are excluded — they'd literally draw the crash
into the map. (A reconstructed centerline from the sim's undocumented
lateral-offset channel was tried first and reverted: wrong-sign flips
put the corridor in the scenery. **Lesson: revert fast when the data
source can't be trusted; find evidence you can generate yourself.**)

### The launcher saga
Windows App Control intermittently blocked the venv's python.exe; the
launcher grew a two-path fallback that misfired silently, and "works on
my shell" turned out to be environment contamination (PYTHONPATH set in
the dev shell, absent on a double-click). Now: one deterministic
environment for any interpreter, engine output captured to
data\engine.log, and the browser only opens once the engine actually
answers. **Lesson: test in the user's environment, not yours — and make
failures leave evidence.**

### Library today
529 laps · 91 sessions · 12 tracks · 104 captured rival laps · 3 classes.

---

## Design principles that emerged (running list)

1. **Wall off what varies.** One adapter per sim; everything else is shared.
2. **Build the test double first.** The simulated driver made every later
   bug diagnosable by elimination.
3. **Compare by position, not time.** Choose the domain where the phenomena
   you care about line up.
4. **Ship the mechanism, not the feature.** Lap files now; world records
   later, for free.
5. **Reality is the best test suite.** Four bugs in one live session, each
   invisible in simulation, each found because a number looked *specifically*
   wrong.
6. **Prefer the authoritative verdict.** Game scoring for lap times and cut
   detection; our own clock only as a sanity check.
