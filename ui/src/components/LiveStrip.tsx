// Compact live readout fed by the WebSocket — the seed of the future
// in-game overlay widgets (same data feed, different window).

import type { LiveFrame } from "../api";
import { fmtTime } from "../api";

export default function LiveStrip({ frame }: { frame: LiveFrame | null }) {
  if (!frame) return null;
  const gear = frame.gear === 0 ? "N" : frame.gear === -1 ? "R" : String(frame.gear);
  return (
    <div className="live-strip">
      <div className="live-cell">
        <div className="label">Speed</div>
        <div className="value">{Math.round(frame.speed * 3.6)}</div>
      </div>
      <div className="live-cell" style={{ minWidth: 34 }}>
        <div className="label">Gear</div>
        <div className="value">{gear}</div>
      </div>
      <div className="pedal-bars">
        <div className="bar">
          <div className="fill throttle" style={{ height: `${frame.throttle * 100}%` }} />
        </div>
        <div className="bar">
          <div className="fill brake" style={{ height: `${frame.brake * 100}%` }} />
        </div>
      </div>
      <div className="live-cell" style={{ minWidth: 90 }}>
        <div className="label">Lap</div>
        <div className="value">{fmtTime(frame.lap_time)}</div>
      </div>
      <div className="live-cell" style={{ minWidth: 90 }}>
        <div className="label">Last</div>
        <div className="value">{fmtTime(frame.last_lap_time)}</div>
      </div>
      <div className="live-cell" style={{ minWidth: 90 }}>
        <div className="label">Best</div>
        <div className="value" style={{ color: "var(--pb)" }}>{fmtTime(frame.best_lap_time)}</div>
      </div>
    </div>
  );
}
