// Live dashboard: track map with racing line + car dot, and the numbers
// that matter while a session is running. Fed by the WebSocket.

import { useEffect, useState } from "react";
import type { LapChannels, LiveFrame, Status } from "../api";
import { fmtTime, getLapData, getPB } from "../api";
import LiveMap from "./LiveMap";

interface Props {
  frame: LiveFrame | null;
  status: Status | null;
}

export default function LiveView({ frame, status }: Props) {
  const [refLine, setRefLine] = useState<LapChannels | null>(null);
  const [refKey, setRefKey] = useState("");

  // Fetch the PB lap's racing line whenever the track/car combo changes.
  useEffect(() => {
    const s = status?.session;
    if (!s || !s.track) return;
    const key = `${s.game}|${s.track}|${s.car_class || s.car}`;
    if (key === refKey) return;
    setRefKey(key);
    getPB(s.game, s.track, s.car, s.car_class || "")
      .then((pb) => (pb ? getLapData(pb.id) : null))
      .then((data) => setRefLine(data as LapChannels | null))
      .catch(() => setRefLine(null));
  }, [status, refKey]);

  const gear = frame ? (frame.gear === 0 ? "N" : frame.gear === -1 ? "R" : String(frame.gear)) : "–";

  return (
    <div className="live-grid">
      <div className="panel" style={{ marginBottom: 0 }}>
        <h3>Track · racing line (PB) + live position</h3>
        <LiveMap frame={frame} refLine={refLine} />
      </div>

      <div className="live-cells">
        <div className="cell" style={{ gridColumn: "1 / -1" }}>
          <div className="label">Speed</div>
          <div className="value">
            {frame ? Math.round(frame.speed * 3.6) : "–"}
            <span className="unit">km/h</span>
          </div>
          <div className="hbar">
            <div
              className="fill rpm"
              style={{ width: `${frame ? Math.min((frame.speed * 3.6) / 340, 1) * 100 : 0}%` }}
            />
          </div>
        </div>

        <div className="cell">
          <div className="label">Gear</div>
          <div className="value">{gear}</div>
        </div>
        <div className="cell">
          <div className="label">RPM</div>
          <div className="value small">{frame ? Math.round(frame.rpm) : "–"}</div>
          <div className="hbar">
            <div className="fill rpm" style={{ width: `${frame ? Math.min(frame.rpm / 9000, 1) * 100 : 0}%` }} />
          </div>
        </div>

        <div className="cell">
          <div className="label">Throttle</div>
          <div className="value small">{frame ? Math.round(frame.throttle * 100) : 0}%</div>
          <div className="hbar">
            <div className="fill throttle" style={{ width: `${frame ? frame.throttle * 100 : 0}%` }} />
          </div>
        </div>
        <div className="cell">
          <div className="label">Brake</div>
          <div className="value small">{frame ? Math.round(frame.brake * 100) : 0}%</div>
          <div className="hbar">
            <div className="fill brake" style={{ width: `${frame ? frame.brake * 100 : 0}%` }} />
          </div>
        </div>

        <div className="cell">
          <div className="label">Current Lap</div>
          <div className="value small">{frame ? fmtTime(frame.lap_time) : "–"}</div>
        </div>
        <div className="cell">
          <div className="label">Last Lap</div>
          <div className="value small">{frame ? fmtTime(frame.last_lap_time) : "–"}</div>
        </div>
        <div className="cell">
          <div className="label">Session Best</div>
          <div className="value small" style={{ color: "var(--pb)" }}>
            {frame ? fmtTime(frame.best_lap_time) : "–"}
          </div>
        </div>
        <div className="cell">
          <div className="label">Lap #</div>
          <div className="value small">{frame ? frame.lap_number : "–"}</div>
        </div>
      </div>
    </div>
  );
}
