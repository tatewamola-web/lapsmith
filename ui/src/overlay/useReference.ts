// Shared by every widget: picks the reference lap for the current
// track + class and re-fetches when the combo or the chosen mode changes.
//   "fastest" — fastest lap in the library, yours or a captured rival's
//   "pb"      — your own personal best only

import { useEffect, useRef, useState } from "react";
import type { LapChannels, LapMeta } from "../api";
import { getLapData, getLaps, getStatus } from "../api";

export type RefMode = "fastest" | "pb";

export function useReference(mode: RefMode = "fastest") {
  const [lap, setLap] = useState<LapChannels | null>(null);
  const [meta, setMeta] = useState<LapMeta | null>(null);
  const key = useRef("");

  useEffect(() => {
    key.current = ""; // mode changed: force a re-pick
    const pick = async () => {
      try {
        const s = await getStatus();
        const sess = s.session;
        if (!sess?.track) return;
        const k = `${mode}|${sess.game}|${sess.track}|${sess.car_class || sess.car}`;
        if (k === key.current) return;
        const laps = await getLaps();
        const candidates = laps.filter(
          (l) =>
            l.track === sess.track &&
            (sess.car_class ? l.car_class === sess.car_class : l.car === sess.car) &&
            l.valid &&
            l.has_data !== false &&
            (mode === "fastest" || l.source !== "opponent")
        );
        key.current = k;
        if (!candidates.length) {
          setLap(null);
          setMeta(null);
          return;
        }
        const best = candidates.reduce((a, b) => (a.lap_time <= b.lap_time ? a : b));
        setMeta(best);
        setLap((await getLapData(best.id)) as LapChannels);
      } catch {
        /* engine offline; retry next tick */
      }
    };
    pick();
    const h = setInterval(pick, 7000);
    return () => clearInterval(h);
  }, [mode]);

  return { lap, meta };
}

/** Reference lap's elapsed time at a given distance (linear interpolation). */
export function refTimeAt(ref: LapChannels, dist: number): number | null {
  const d = ref.lap_dist;
  const t = ref.lap_time;
  if (!d.length || dist < d[0] || dist > d[d.length - 1]) return null;
  let lo = 0;
  let hi = d.length - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (d[mid] <= dist) lo = mid;
    else hi = mid;
  }
  const f = (dist - d[lo]) / (d[hi] - d[lo] || 1);
  return t[lo] + f * (t[hi] - t[lo]);
}

/** Widget settings stored in the engine (shared by web UI and widgets). */
export interface WidgetSettings {
  delta?: { range: number; ref: RefMode; showBar: boolean; showNumber: boolean };
  telemetry?: { ref: RefMode };
}

export const DEFAULT_DELTA = { range: 1.0, ref: "fastest" as RefMode, showBar: true, showNumber: true };

export function useWidgetSettings(): WidgetSettings {
  const [s, setS] = useState<WidgetSettings>({});
  useEffect(() => {
    const load = () =>
      fetch("/api/widgets/settings")
        .then((r) => r.json())
        .then(setS)
        .catch(() => {});
    load();
    const h = setInterval(load, 3000); // pick up changes made in the web UI
    return () => clearInterval(h);
  }, []);
  return s;
}
