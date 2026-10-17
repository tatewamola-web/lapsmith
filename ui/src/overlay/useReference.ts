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
export interface TelemetrySettings {
  enabled?: boolean;
  ref: RefMode;
  trace: boolean;
  inputs: boolean;
  gear: boolean;
  times: boolean;
  horizontal: boolean;
  autohide: boolean;
}
export interface DeltaSettings {
  enabled?: boolean;
  range: number;
  ref: RefMode;
  showBar: boolean;
  showNumber: boolean;
}
export interface CalloutSettings {
  enabled?: boolean;
  lead: number; // meters before the apex the callout appears
}
export interface WidgetSettings {
  general?: { autohide?: boolean }; // hide every widget in menus/garage
  delta?: Partial<DeltaSettings>;
  telemetry?: Partial<TelemetrySettings>;
  callouts?: Partial<CalloutSettings>;
}

export const DEFAULT_DELTA: DeltaSettings = { range: 1.0, ref: "fastest", showBar: true, showNumber: true };
export const DEFAULT_TELEMETRY: TelemetrySettings = {
  ref: "fastest", trace: true, inputs: true, gear: true, times: true,
  horizontal: false, autohide: true,
};
export const DEFAULT_CALLOUTS: CalloutSettings = { lead: 250 };

/** Global "Hide in menus" (falls back to on). */
export function hideInMenus(settings: WidgetSettings): boolean {
  return settings.general?.autohide ?? true;
}

/** Widgets close themselves when switched off in the hub — the hub never
 * needs a direct line to the widget windows, only to the engine. */
export function useCloseWhenDisabled(name: "delta" | "telemetry" | "callouts", settings: WidgetSettings) {
  useEffect(() => {
    if (settings[name]?.enabled === false) window.close();
  }, [name, settings]);
}

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
