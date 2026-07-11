// In-game overlay v2.
// - Trace: a rolling window of the track ahead/behind showing the reference
//   lap's throttle/brake curves (dim) with your actual inputs drawn over
//   them (bright) up to the car's position. The reference is the fastest
//   lap in the library for this track+class — yours or a captured rival's.
// - Inputs: your live pedal bars only.
// - Gear: big digit with the revs wrapping around it as a ring, speed below.

import { useEffect, useRef, useState } from "react";
import type { LapChannels, LapMeta, LiveFrame } from "../api";
import { fmtTime, getLapData, getLaps, getStatus, openLive } from "../api";

interface Toggles {
  trace: boolean;
  inputs: boolean;
  gear: boolean;
  times: boolean;
  horizontal: boolean; // lengthwise layout: everything on one line
  autohide: boolean;   // only visible while actually on track
}

const DEFAULT_TOGGLES: Toggles = {
  trace: true, inputs: true, gear: true, times: true,
  horizontal: false, autohide: true,
};
const TRAIL = 1800; // ~72s of frames for the live trace

export default function Overlay() {
  const [frame, setFrame] = useState<LiveFrame | null>(null);
  const [refLap, setRefLap] = useState<LapChannels | null>(null);
  const [refMeta, setRefMeta] = useState<LapMeta | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [toggles, setToggles] = useState<Toggles>(() => {
    try {
      return { ...DEFAULT_TOGGLES, ...JSON.parse(localStorage.getItem("overlay-toggles-v2") || "{}") };
    } catch {
      return DEFAULT_TOGGLES;
    }
  });
  const comboKey = useRef("");
  const canvasRef = useRef<HTMLCanvasElement>(null);
  // on-track detection: the engine only streams frames while the sim is
  // live — silence means menus/garage
  const lastMsgAt = useRef(0);
  const [onTrack, setOnTrack] = useState(false);
  // my recent inputs by distance, cleared each new lap
  const trail = useRef<{ d: number; thr: number; brk: number }[]>([]);
  const lastLapNo = useRef(-1);
  const maxRpm = useRef(8000);

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

  // reference = fastest lap with telemetry for this track+class, any driver
  useEffect(() => {
    const pick = async () => {
      try {
        const s = await getStatus();
        const sess = s.session;
        if (!sess?.track) return;
        const key = `${sess.game}|${sess.track}|${sess.car_class || sess.car}`;
        if (key === comboKey.current) return;
        const laps = await getLaps();
        const candidates = laps.filter(
          (l) =>
            l.track === sess.track &&
            (sess.car_class ? l.car_class === sess.car_class : l.car === sess.car) &&
            l.valid &&
            l.has_data !== false
        );
        if (!candidates.length) {
          comboKey.current = key;
          setRefLap(null);
          setRefMeta(null);
          return;
        }
        const best = candidates.reduce((a, b) => (a.lap_time <= b.lap_time ? a : b));
        comboKey.current = key;
        setRefMeta(best);
        setRefLap((await getLapData(best.id)) as LapChannels);
      } catch {
        /* engine offline; retry */
      }
    };
    pick();
    const h = setInterval(pick, 7000);
    return () => clearInterval(h);
  }, []);

  // accumulate my inputs; reset on new lap
  useEffect(() => {
    if (!frame) return;
    if (frame.lap_number !== lastLapNo.current) {
      lastLapNo.current = frame.lap_number;
      trail.current = [];
    }
    trail.current.push({ d: frame.lap_dist, thr: frame.throttle, brk: frame.brake });
    if (trail.current.length > TRAIL) trail.current.shift();
    if (frame.rpm > maxRpm.current) maxRpm.current = frame.rpm;
  }, [frame]);

  // trace canvas
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !toggles.trace) return;
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth;
    const h = canvas.clientHeight || 84;
    if (canvas.width !== w * dpr) canvas.width = w * dpr;
    if (canvas.height !== h * dpr) canvas.height = h * dpr;
    const ctx = canvas.getContext("2d")!;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    if (!frame) return;

    const back = 480; // meters behind the car
    const ahead = 320; // meters ahead
    const d0 = frame.lap_dist - back;
    const d1 = frame.lap_dist + ahead;
    const X = (d: number) => ((d - d0) / (d1 - d0)) * w;
    const Y = (v: number) => h - 3 - v * (h - 8);

    // reference curves for the window (dim)
    if (refLap) {
      const step = refLap.lap_dist.length > 1 ? refLap.lap_dist[1] - refLap.lap_dist[0] : 4;
      const iA = Math.max(Math.floor(d0 / step), 0);
      const iB = Math.min(Math.ceil(d1 / step), refLap.lap_dist.length - 1);
      const drawRef = (arr: number[], color: string) => {
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        ctx.beginPath();
        for (let i = iA; i <= iB; i++) {
          const px = X(i * step);
          i === iA ? ctx.moveTo(px, Y(arr[i])) : ctx.lineTo(px, Y(arr[i]));
        }
        ctx.stroke();
      };
      drawRef(refLap.throttle, "rgba(46,160,67,0.6)");
      drawRef(refLap.brake, "rgba(218,54,51,0.65)");
    }

    // my actual inputs up to the car (bright)
    const t = trail.current;
    const drawMine = (getV: (p: { thr: number; brk: number }) => number, color: string) => {
      // dark underlay first so the line pops against any game background
      for (const [c, w] of [["rgba(0,0,0,0.85)", 4.5], [color, 2.6]] as const) {
        ctx.strokeStyle = c as string;
        ctx.lineWidth = w as number;
        ctx.beginPath();
        let started = false;
        for (const p of t) {
          if (p.d < d0 || p.d > frame.lap_dist) continue;
          const px = X(p.d);
          started ? ctx.lineTo(px, Y(getV(p))) : ctx.moveTo(px, Y(getV(p)));
          started = true;
        }
        ctx.stroke();
      }
    };
    drawMine((p) => p.thr, "#3fb950");
    drawMine((p) => p.brk, "#f85149");

    // car position line
    ctx.strokeStyle = "rgba(232,234,237,0.8)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(X(frame.lap_dist), 2);
    ctx.lineTo(X(frame.lap_dist), h - 2);
    ctx.stroke();
  }, [frame, refLap, toggles.trace]);

  const save = (t: Toggles) => {
    setToggles(t);
    localStorage.setItem("overlay-toggles-v2", JSON.stringify(t));
  };

  const gear = frame ? (frame.gear === 0 ? "N" : frame.gear === -1 ? "R" : String(frame.gear)) : "–";
  const rpmFrac = frame ? Math.min(frame.rpm / maxRpm.current, 1) : 0;
  const ringColor = rpmFrac > 0.92 ? "#f85149" : rpmFrac > 0.8 ? "#d4a017" : "#4dd0e1";
  const R = 26;
  const CIRC = 2 * Math.PI * R;
  const refLabel = refMeta
    ? refMeta.driver === "me"
      ? `PB ${fmtTime(refMeta.lap_time)}`
      : `${refMeta.driver.split(" ")[0]} ${fmtTime(refMeta.lap_time)}`
    : "no reference yet";

  const hidden = toggles.autohide && !onTrack;

  return (
    <div className={`ovl ${toggles.horizontal ? "horizontal" : ""} ${hidden ? "faded" : ""}`}>
      <div className="ovl-grip" title="drag to move" />
      <button className="ovl-gear" onClick={() => setMenuOpen(!menuOpen)}>⚙</button>

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
          <div className="ovl-hint">
            ref: {refLabel} · Ctrl+Alt+O click-through · Ctrl+Alt+H hide · resize corners to scale
          </div>
          <button className="ovl-close" onClick={() => window.close()}>✕ close overlay</button>
        </div>
      )}

      {toggles.trace && (
        <div className="ovl-trace">
          <canvas ref={canvasRef} style={{ width: "100%", height: 84 }} />
        </div>
      )}

      <div className="ovl-mid">
        {toggles.inputs && (
          <div className="pbars">
            <div className="pbar"><div className="pfill throttle" style={{ height: `${(frame?.throttle ?? 0) * 100}%` }} /></div>
            <div className="pbar"><div className="pfill brake" style={{ height: `${(frame?.brake ?? 0) * 100}%` }} /></div>
          </div>
        )}
        {toggles.gear && (
          <div className="gear-ring">
            <svg width="70" height="70" viewBox="0 0 70 70">
              <circle cx="35" cy="35" r={R} fill="none" stroke="rgba(38,45,54,0.9)" strokeWidth="5" />
              <circle
                cx="35" cy="35" r={R} fill="none"
                stroke={ringColor} strokeWidth="5" strokeLinecap="round"
                strokeDasharray={`${rpmFrac * CIRC} ${CIRC}`}
                transform="rotate(-90 35 35)"
              />
              <text x="35" y="44" textAnchor="middle" fill="#e8eaed" fontSize="26" fontWeight="700">
                {gear}
              </text>
            </svg>
            <div className="gear-speed">
              {frame ? Math.round(frame.speed * 2.23694) : "–"} <span>mph</span>
            </div>
          </div>
        )}
      </div>

      {toggles.times && (
        <div className="ovl-row times">
          <span>LAP {frame ? fmtTime(frame.lap_time) : "–"}</span>
          <span>LAST {frame ? fmtTime(frame.last_lap_time) : "–"}</span>
          <span className="gold">BEST {frame ? fmtTime(frame.best_lap_time) : "–"}</span>
        </div>
      )}
    </div>
  );
}
