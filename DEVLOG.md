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

## 2026-07-19 → 07-24 — Week 3: The coach gets smart, the plumbing gets fixed

### Two mysteries closed at once
Engines kept dying hours after they started. The cause turned out to be the
development harness, not the app: processes spawned inside a tool session
are reaped when that session is torn down — so *my* restarts died while the
user's double-clicks never did, which is exactly why it looked unreproducible
for a week. Separately, the uv-managed Python interpreter got relocated
twice and blocked once by Windows App Control, leaving the venv pointing at
nothing. Fixes: the engine is launched out-of-tree via WMI, the venv was
rebuilt on the signed python.org 3.12, the launcher *proves* a candidate
interpreter can import the engine before trusting it, and the engine writes
its own log so a death always leaves evidence.
**Lesson: when a bug won't reproduce for you but does for the user, suspect
your environment, not their description.**

### ABS detection without an ABS channel
The sim never publishes "ABS engaged" — but it publishes per-wheel brake
pressure, and ABS *is* pressure fluttering while the pedal is held. Detect
the flutter, get the flag. Those samples render amber over the brake trace
in both the app and the overlay.
**Lesson: the signal you want is often a derivative of a signal you have.**

### Coach v3: gradient boosting with counterfactual gains
The linear coach could only ever say "do what your best lap did", and for a
consistent driver those gains are tiny. Two upgrades: a **benchmark tier**
comparing your best corner against the fastest traversal ever recorded there
(captured rival laps included — so racing quicker people literally improves
your coaching), and **scikit-learn gradient boosting** replacing least
squares. Trees capture interactions a line can't, and the per-habit value is
read out counterfactually: predict corner time at your median habits, change
one feature to your best-lap value, predict again — the difference is what
that habit is worth. On real data it re-ranked the top recommendation and
valued it 30% higher than the linear estimate.
**Lesson: a fitted model is a question-answering machine; asking it
counterfactuals is how you make a black box explain itself.**

### Interface maturity
Crosshair value chips on every chart, both maps following the cursor, a gear
trace, collapsible panels that remember their state, and the analysis
sidebar grouping strictly by class (rival laps were arriving without a class
and fragmenting the list into one entry per car — fixed at the source and
backfilled). Corner-name anchors now self-calibrate: when detection finds
exactly as many corners as a track's name list holds, the names map in order
and rough map-derived percentages stop mattering.

---

## 2026-10-16 — Widgets become a system

### Delta bar + a Widgets tab
The single overlay became a widget host: one Electron process, one window
per widget, each with its own saved position and size, selected by a URL
parameter on a shared page. First new widget: an iRacing-style **delta bar** —
live gap to the reference lap, computed client-side by interpolating the
reference lap's elapsed time at the car's current distance (the same
compare-by-position idea as the analysis charts, run 25 times a second).
The bar shows *where you stand*; the number's color shows *which way it's
moving*, since "still behind but gaining" is the thing a driver can act on.

A new **Widgets** tab launches and configures them. Settings live in the
engine (`data/widgets.json`) rather than browser storage, because the web UI
and the Electron windows have separate storage — but both talk to the engine.
**Lesson: put shared state where every reader can reach it.**

---

## 2026-10-17 — Corner callouts and a real widget hub

### Callouts: from analysis to instruction
The coach's findings were written for reading after a session ("the fastest
driver here brakes 12m later, carries 5mph more…"). A driver at 150mph gets
about one glance. So the coach now also emits a callout per corner — the raw
differences (braking point, minimum speed, throttle point) bucketed into at
most two plain verbs: *"Brake slightly later, throttle sooner"*. The widget
shows it a configurable distance before the apex and clears after.
**Lesson: the same insight needs different packaging for different moments —
detail for the debrief, a verb for the corner.**

### The hub owns the widgets
Widget settings moved out of the widgets' own gear menus into the Widgets
tab, along with on/off switches. Turning a widget off doesn't need any
connection to its window: the widget polls its settings from the engine and
closes itself when it sees `enabled: false`. One source of truth, no IPC.

---

## 2026-10-17 (later): Lapsmith gets a voice

### A neural voice, not a robot
Windows' built-in speech is the robotic SAPI voice. Lapsmith instead runs
Piper, an open-source neural text-to-speech model, locally: 0.7s to
synthesize three seconds of speech, and every phrase is cached as a WAV so
repeated callouts play instantly. Written callouts get rewritten for the ear
("T1 · Brake slightly later, throttle sooner" becomes "Turn one. Brake a
touch later, then throttle sooner.") and trigger about 3.5 seconds of travel
ahead of the corner, so the sentence ends before the braking zone.

### Spotter (beta): calibrated from data, not assumed
Telling left from right means knowing the handedness of LMU's world
coordinates, and getting it backwards would make a spotter dangerous rather
than useless. Instead of guessing, the engine's recorded laps answered it:
across 13,400 samples, steering right rotated the heading toward the
negative cross-product side 99.2% of the time. Each nearby car is projected
onto the player's heading and its normal; overlap within a car length means
"alongside". A 0.35s hold stops flicker, and spotter calls cut off coaching
mid-sentence. It was tested against synthetic traffic first (right, three
wide, clear right, clear left, far car ignored) before ever speaking in a
real race.
**Lesson: when a mistake would be dangerous, measure the convention instead
of assuming it.**

---

## 2026-11-15: "On" has to mean on

First real session with widgets after a restart: the hub showed Delta and
Input Trace switched on, but nothing appeared in game. "Enabled" was only a
saved preference. Windows opened when the switch was flipped, and nothing
reopened them after a reboot. The engine now relaunches every enabled
widget a few seconds after it starts, so the switch describes what's
actually on screen.
**Lesson: a setting that only takes effect on the moment it's changed is a
button pretending to be a switch.**

---

## 2026-11-15 (later): The stutter, and an engineer on the radio

### Why the input trace got laggy
Measured, not guessed: the engine's own per-frame work (reading every car,
recording rivals, the spotter) totals under 0.3 ms against a 20 ms budget,
so recording wasn't it. The culprit was the web app re-downloading the whole
lap library every 3 seconds: 441 KB and ~156 ms of Python work per request,
which starved the thread streaming frames to the widgets and caused a hitch
every few seconds. It only appeared once the library passed a thousand laps.
Fix: the library carries a version number, the server caches the serialized
lap list until that version changes, and the app only re-fetches when it
does. The live stream also went from 25 to 50 updates a second.
**Lesson: in a real-time system, a slow request anywhere can become jank
everywhere. Profile the whole process, not just the hot loop.**

### Engineer voice
The voice now reports the car's health: fuel warnings stepping down from
"fuel for about three laps" to "fuel is critical, box this lap" (consumption
averaged over the last three laps), punctures and slow leaks by corner of
the car, lost wheels and parts, contact damage, and overheating. Each event
is spoken once. The spotter gained "Still there, hold your line" while a car
stays alongside, plus "hold your line" when three wide.

---

## 2026-11-15 (night): Field-test fixes

The first real race with voice and widgets surfaced three problems:

- **Widgets still stuttering.** Chromium deliberately slows windows that
  don't have focus, and while driving the game always has focus; the
  overlays now opt out (`backgroundThrottling: false`). Piper's speech
  synthesis also defaulted to every CPU core, so a burst of new phrases
  mid-race could steal time from the game; it's now capped at two threads on
  a below-normal-priority thread.
- **Delta bar stuck on "no reference".** The reference picker checked once
  per track/class, found no laps (a brand-new combo), and never looked
  again. It now re-checks whenever the lap library changes.
- **A crash triggered a flood of voice messages.** Each bounce and every
  broken part was its own message. Damage is now handled as one *incident*:
  events are collected for 1.5 seconds, then the engineer says one sentence
  ("Puncture front left, and heavy damage. Box this lap."), keeps quiet for
  12 seconds unless something worse happens, mutes the spotter during the
  incident, and never repeats a sentence within 4 seconds.
**Lesson: real-time feedback has to be rate-limited by meaning, not by
event count. One crash is one event to a driver, however many signals the
car emits.**

---

## 2026-11-15 (late): The 5 Hz distance bug

The live delta flickered between plus and minus and the input trace
skipped. Measured on a recorded lap: in **90% of frames the car's lap
distance didn't move at all**, then it jumped ~9 m. LMU publishes lap
distance in its scoring buffer, which only updates about five times a
second, while everything else arrives at 50 Hz. Lap time kept ticking while
distance froze, so the delta sawed by ~0.18 s every fifth of a second.
Recorded laps had silently been losing distance resolution the same way
since day one.

Fix: the scoring snapshot is stamped with the time it describes, so the
adapter advances that distance by speed × elapsed time for every telemetry
frame (never backwards within a lap). On a simulated car the error went from
10.8 m to zero.
**Lesson: when two data streams update at different rates, every value
computed from both inherits the slower rate unless you interpolate it.**
This is the same lesson as day two's scoring-lag bug, found again in a new
place.

Also: the delta number is now green only when actually ahead of the
reference; the engineer reads lap times ("One seventeen point three.
Personal best."), and there's a choice of voices including British ones.

---

## 2026-11-15 (later still): Measured while driving

Tate drove while a probe recorded the live stream. The distance fix held
(frozen frames 90% → 1%), but the stream ran at **15 frames/s with a
595 ms stall**, which was the real lag. Two causes:

1. **Windows timer resolution.** `sleep(0.02)` lasts ~31 ms on Windows
   (15.6 ms timer steps), and the loop slept a fixed interval *after* its
   work, so 50 Hz drifted toward 30 Hz. Fix: `timeBeginPeriod(1)` plus
   deadline-based pacing.
2. **Disk writes in the real-time loop.** Every finished lap, the player's
   or any rival's, was compressed, written and pruned inside the 50 Hz loop.
   With a full grid, someone finishes a lap every few seconds, and each save
   froze the feed. Fix: completed laps go to a writer thread.

Result on a test engine: 47 frames/s, worst gap 48 ms while saving a lap.
**Lesson: never do I/O on a real-time path, and on Windows never trust
sleep() to mean what it says.**

Measured again on the live session: 29 frames/s. Better, but still short.
Sampling LMU at 2 ms showed it publishes exactly 50 frames/s, and the
engine also read at 50 Hz, so the two clocks drifted in and out of phase:
some frames were read twice, others skipped entirely (aliasing). The
engine now checks LMU at 200 Hz and only processes a frame when its
timestamp is new. Live result: **46 frames/s, worst gap 62 ms**, up from
15 frames/s and 595 ms at the start of the evening.
**Lesson: to capture every sample of a periodic source, poll it faster
than it publishes, and deduplicate.**

---

## 2026-11-15 (end of night): Faster, plainer damage calls

After a wall hit, the engineer took a few seconds to speak. Three delays
stacked up: a 1.5 s wait for the crash to finish, synthesizing a sentence
nobody had heard before, and queueing behind any callout already playing.
Now the wait is 0.6 s, every possible damage sentence (35 of them) is
synthesized at startup so it plays instantly, and damage reports interrupt
coaching. Wording is plainer too, per Tate: light, medium, or heavy damage,
plus the puncture or lost wheel if there is one ("Puncture front left,
heavy damage. Box this lap."). A test also caught a real bug: crashes that
started from an undamaged car were always called "light", because a
starting value of 0 was treated as "no value" (`0 or x` in Python).
Lap-time announcements now default off; LMU already reads them out.

---

## 2026-11-15 (one more): LMU's own damage data, and the 2-second localhost trap

The rF2 shared memory Lapsmith reads has dents and lost parts, but not what
LMU's damage screen shows. LMU also runs a local REST API (port 6397, the
one its own UI uses), and `getVehicleCondition` there has per-corner
suspension damage (0 to 1), body damage, tyre and brake condition; the
repair screen adds virtual energy. The adapter now polls it on a background
thread, so the engineer can call suspension damage by corner in LMU's
colour bands (light/yellow, medium/orange, heavy/red, broken) and warn on
virtual energy like fuel.

Engine condition isn't in any of LMU's data, so a dead engine is detected
from first principles: revs collapsing below 300 while the car still rolls,
outside the pits, for 1.5 s.

Reports are now assembled from ~30 short pre-synthesized pieces ("Puncture
front left." + "Rear right suspension's broken." + "Box this lap.") instead
of one recording per combination, which would have been 1,000+.

The REST data first arrived empty: every request took 2 seconds and hit the
timeout. `localhost` resolves to IPv6 first on Windows, LMU listens on IPv4
only, and Python waits ~2 s before falling back; `127.0.0.1` answers in
25 ms. The widget windows now load from 127.0.0.1 for the same reason.
**Lesson: "localhost" is a name, not an address. When latency is exactly
round numbers of seconds, suspect a timeout or fallback, not slowness.**

---

## 2026-11-15 (calibration): Matching LMU's damage colours

Field report: a light touch with no visible damage was called "light
damage", and a pit-lane crash that turned the front orange was also called
"light". Reading the car's state right after showed why. rF2/LMU track body
damage in 8 zones, each 0/1/2, and the orange front zone read 2. LMU's
screen is literally drawing those zones: 1 = yellow, 2 = orange, a part
gone = red. The engineer had been counting total new dents instead, so a
zone jumping to orange (+2) still looked "light", and a one-dent touch
spoke up.

Now severity is the worst zone that got worse (yellow → light, orange →
medium, part lost → heavy), and a zone turning yellow from a tiny impact is
treated as a touch and stays silent. That impact cut-off is a guess, so
every incident now logs its zone values, impact size, and parts lost to
engine.log to be tuned from real crashes.
**Lesson: when software interprets the same data a human sees on screen,
calibrate against the screen, not your intuition about the numbers.**

---

## 2026-11-15 (last): A spotter has to be instant

Field report: car calls came late. Three delays: every call waited 0.35 s
of confirmation, the spotter was muted for the full 10 s after any damage
report, and a car only counted once it fully overlapped. Now a car
appearing is confirmed in 0.1 s (clearing still waits 0.4 s so a tight
battle doesn't flicker between "car left" and "clear"), the mute lasts only
through the crash plus 2 s, and the overlap window starts a metre earlier.
A timing test caught that the first "still there" was also waiting on the
3 s repeat timer; it now comes at 2 s. Measured: "Car left" 0.11 s after
the car arrives.
**Lesson: debounce asymmetrically. Being late to say "car left" is worse
than being late to say "clear".**

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
