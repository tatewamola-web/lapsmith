// Corner coach callouts: as you approach a corner, its single most useful
// instruction appears — "T1 · Brake slightly later, throttle sooner" — then
// fades after the apex. Callouts come from the coach (your habits + the
// fastest driving recorded here) and refresh when the track or class changes.

import { useEffect, useRef, useState } from "react";
import type { LiveFrame } from "../api";
import { getStatus, openLive } from "../api";
import { DEFAULT_CALLOUTS, useCloseWhenDisabled, useWidgetSettings } from "./useReference";

interface Callout {
  corner: string;
  apex_dist: number;
  text: string;
}

export default function CalloutWidget() {
  const settings = useWidgetSettings();
  useCloseWhenDisabled("callouts", settings);
  const lead = settings.callouts?.lead ?? DEFAULT_CALLOUTS.lead;

  const [frame, setFrame] = useState<LiveFrame | null>(null);
  const [callouts, setCallouts] = useState<Callout[]>([]);
  const comboKey = useRef("");

  useEffect(() => openLive(setFrame), []);

  // Fetch callouts when the track/class changes (checked every 10s), and
  // re-pull every 3 minutes so laps driven this session sharpen them.
  useEffect(() => {
    let lastFetch = 0;
    const load = async () => {
      try {
        const sess = (await getStatus()).session;
        if (!sess?.track) return;
        const key = `${sess.track}|${sess.car_class || sess.car}`;
        if (key === comboKey.current && Date.now() - lastFetch < 180000) return;
        comboKey.current = key;
        lastFetch = Date.now();
        const q = new URLSearchParams({ track: sess.track, car_class: sess.car_class || "", car: sess.car });
        const d = await (await fetch(`/api/coach?${q}`)).json();
        setCallouts((d.callouts ?? []) as Callout[]);
      } catch {
        /* engine offline; retry next tick */
      }
    };
    load();
    const h = setInterval(load, 10000);
    return () => clearInterval(h);
  }, []);

  // the next corner ahead within the lead distance (or just past its apex)
  let active: Callout | null = null;
  if (frame) {
    for (const c of callouts) {
      const ahead = c.apex_dist - frame.lap_dist;
      if (ahead <= lead && ahead >= -40) {
        active = c;
        break;
      }
    }
  }

  return (
    <div className={`cw ${active ? "show" : ""}`}>
      <div className="cw-grip" />
      {active && (
        <div className="cw-chip">
          <span className="cw-corner">{active.corner}</span>
          <span className="cw-text">{active.text}</span>
        </div>
      )}
    </div>
  );
}
