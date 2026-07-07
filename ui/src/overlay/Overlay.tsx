// In-game overlay: your live pedal inputs next to what your PB lap did at
// this exact point of the track — "the ideal inputs" ghosting your own.
// Widgets are toggleable (gear menu), the window is moved by dragging the
// grip bar and resized from its edges (Electron frameless window).

import { useEffect, useRef, useState } from "react";
import type { LapChannels, LiveFrame } from "../api";
import { fmtTime, getLapData, getPB, getStatus, openLive } from "../api";

interface Toggles {
  pedals: boolean;
  speed: boolean;
  times: boolean;
}

const DEFAULT_TOGGLES: Toggles = { pedals: true, speed: true, times: true };

export default function Overlay() {
  const [frame, setFrame] = useState<LiveFrame | null>(null);
  const [pbLap, setPbLap] = useState<LapChannels | null>(null);
  const [pbTime, setPbTime] = useState<number | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [toggles, setToggles] = useState<Toggles>(() => {
    try {
      return { ...DEFAULT_TOGGLES, ...JSON.parse(localStorage.getItem("overlay-toggles") || "{}") };
    } catch {
      return DEFAULT_TOGGLES;
    }
  });
  const comboKey = useRef("");

  useEffect(() => openLive(setFrame), []);

  // fetch the PB lap (the "ideal" inputs) whenever track/class changes
  useEffect(() => {
    const h = setInterval(async () => {
      try {
        const s = await getStatus();
        const sess = s.session;
        if (!sess?.track) return;
        const key = `${sess.game}|${sess.track}|${sess.car_class || sess.car}`;
        if (key === comboKey.current) return;
        comboKey.current = key;
        const pb = await getPB(sess.game, sess.track, sess.car, sess.car_class || "");
        if (pb && pb.has_data !== false) {
          setPbTime(pb.lap_time);
          setPbLap((await getLapData(pb.id)) as LapChannels);
        } else {
          setPbTime(pb?.lap_time ?? null);
          setPbLap(null);
        }
      } catch {
        /* engine offline; retry next tick */
      }
    }, 5000);
    return () => clearInterval(h);
  }, []);

  const save = (t: Toggles) => {
    setToggles(t);
    localStorage.setItem("overlay-toggles", JSON.stringify(t));
  };

  // PB ("ideal") inputs at the car's current track position
  let pbThrottle = 0;
  let pbBrake = 0;
  if (pbLap && frame) {
    const step = pbLap.lap_dist.length > 1 ? pbLap.lap_dist[1] - pbLap.lap_dist[0] : 4;
    const i = Math.min(Math.max(Math.round(frame.lap_dist / step), 0), pbLap.throttle.length - 1);
    pbThrottle = pbLap.throttle[i];
    pbBrake = pbLap.brake[i];
  }

  const gear = frame ? (frame.gear === 0 ? "N" : frame.gear === -1 ? "R" : String(frame.gear)) : "–";

  return (
    <div className="ovl">
      <div className="ovl-grip">
        <span className="ovl-title">LAPSMITH</span>
        <span className="ovl-sub">{frame ? "" : "waiting for telemetry"}</span>
        <button className="ovl-gear" onClick={() => setMenuOpen(!menuOpen)}>⚙</button>
      </div>

      {menuOpen && (
        <div className="ovl-menu">
          {(Object.keys(DEFAULT_TOGGLES) as (keyof Toggles)[]).map((k) => (
            <label key={k}>
              <input
                type="checkbox"
                checked={toggles[k]}
                onChange={(e) => save({ ...toggles, [k]: e.target.checked })}
              />
              {k}
            </label>
          ))}
          <div className="ovl-hint">Ctrl+Alt+O: click-through · Ctrl+Alt+H: hide</div>
        </div>
      )}

      {toggles.pedals && (
        <div className="ovl-row pedals">
          <div className="pcol">
            <div className="plabel">YOU</div>
            <div className="pbars">
              <div className="pbar"><div className="pfill throttle" style={{ height: `${(frame?.throttle ?? 0) * 100}%` }} /></div>
              <div className="pbar"><div className="pfill brake" style={{ height: `${(frame?.brake ?? 0) * 100}%` }} /></div>
            </div>
          </div>
          <div className="pcol ghost">
            <div className="plabel">PB</div>
            <div className="pbars">
              <div className="pbar"><div className="pfill throttle" style={{ height: `${pbThrottle * 100}%` }} /></div>
              <div className="pbar"><div className="pfill brake" style={{ height: `${pbBrake * 100}%` }} /></div>
            </div>
          </div>
          {toggles.speed && (
            <div className="ovl-speed">
              <div className="big">{frame ? Math.round(frame.speed * 3.6) : "–"}</div>
              <div className="small">km/h · {gear}</div>
            </div>
          )}
        </div>
      )}

      {toggles.times && (
        <div className="ovl-row times">
          <span>LAP {frame ? fmtTime(frame.lap_time) : "–"}</span>
          <span>LAST {frame ? fmtTime(frame.last_lap_time) : "–"}</span>
          <span className="gold">PB {fmtTime(pbTime)}</span>
        </div>
      )}
    </div>
  );
}
