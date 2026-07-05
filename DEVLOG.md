# APEX Development Log

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
