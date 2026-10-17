// iRacing-style delta bar: live time gap to the reference lap at the car's
// current track position. The bar fills from the center — green to the
// left when you're ahead, red to the right when you're behind — and the
// number's color shows the TREND: green while you're gaining right now,
// red while you're losing, even if you're still behind overall.

import { useEffect, useRef, useState } from "react";
import type { LiveFrame } from "../api";
import { openLive } from "../api";
import { DEFAULT_DELTA, refTimeAt, useReference, useWidgetSettings } from "./useReference";

export default function DeltaWidget() {
  const settings = useWidgetSettings();
  const cfg = { ...DEFAULT_DELTA, ...settings.delta };
  const { lap: ref } = useReference(cfg.ref);
  const [frame, setFrame] = useState<LiveFrame | null>(null);
  const lastMsgAt = useRef(0);
  const [onTrack, setOnTrack] = useState(false);
  const prevDelta = useRef<{ v: number; t: number } | null>(null);
  const [trend, setTrend] = useState(0); // s per s; negative = gaining

  useEffect(
    () =>
      openLive((f) => {
        lastMsgAt.current = Date.now();
        setFrame(f);
      }),
    []
  );
  useEffect(() => {
    const h = setInterval(() => setOnTrack(Date.now() - lastMsgAt.current < 3000), 1000);
    return () => clearInterval(h);
  }, []);

  let delta: number | null = null;
  if (frame && ref && frame.lap_dist > 30) {
    const rt = refTimeAt(ref, frame.lap_dist);
    if (rt != null) delta = frame.lap_time - rt;
  }

  // smoothed trend over ~0.5s windows
  useEffect(() => {
    if (delta == null) return;
    const now = performance.now();
    const p = prevDelta.current;
    if (!p || now - p.t > 1500) {
      prevDelta.current = { v: delta, t: now };
    } else if (now - p.t > 500) {
      setTrend((delta - p.v) / ((now - p.t) / 1000));
      prevDelta.current = { v: delta, t: now };
    }
  }, [delta]);

  const frac = delta == null ? 0 : Math.max(-1, Math.min(1, delta / cfg.range));
  const numColor = delta == null ? "#8b949e" : trend < -0.005 ? "#3fb950" : trend > 0.005 ? "#f85149" : "#e8eaed";

  return (
    <div className={`dw ${onTrack ? "" : "faded"}`}>
      <div className="dw-grip" title="drag to move" />
      {cfg.showBar && (
        <div className="dw-bar">
          <div className="dw-center" />
          <div
            className="dw-fill"
            style={{
              left: frac < 0 ? `${50 + frac * 50}%` : "50%",
              width: `${Math.abs(frac) * 50}%`,
              background: frac < 0 ? "#3fb950" : "#f85149",
            }}
          />
        </div>
      )}
      {cfg.showNumber && (
        <div className="dw-num" style={{ color: numColor }}>
          {delta == null ? (ref ? "–.––" : "no ref") : `${delta >= 0 ? "+" : "−"}${Math.abs(delta).toFixed(2)}`}
        </div>
      )}
    </div>
  );
}
