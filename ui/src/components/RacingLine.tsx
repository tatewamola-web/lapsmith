// Racing-line view with ghost playback.
//
// Both laps' driven lines are drawn top-down inside an approximate track
// corridor. Press play and both cars lap the circuit on the same clock —
// the classic "ghost" comparison: at every moment you see exactly where
// the reference car is relative to you. Solo mode plays one lap alone.
//
// Interactions: wheel = zoom around cursor, drag = pan, corner chips =
// jump to a corner, double-click = reset view.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ComparePayload, Insights } from "../api";
import { fmtTime } from "../api";

interface Props {
  cmp: ComparePayload;
  insights: Insights | null;
  solo?: boolean;
}

function officialLabel(name: string, n: number): string {
  return name ? name.split(" ")[0] : `T${n}`;
}

/** distance (m) a lap had covered at time t, from its lap_time-over-dist curve */
function distAt(t: number, times: number[], dist: number[]): number {
  if (t <= times[0]) return dist[0];
  if (t >= times[times.length - 1]) return dist[dist.length - 1];
  // times is monotonic; binary search
  let lo = 0, hi = times.length - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (times[mid] <= t) lo = mid;
    else hi = mid;
  }
  const f = (t - times[lo]) / (times[hi] - times[lo] || 1);
  return dist[lo] + f * (dist[hi] - dist[lo]);
}

export default function RacingLine({ cmp, insights, solo = false }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [cornerN, setCornerN] = useState<number | null>(null);
  const [follow, setFollow] = useState(false); // chase-cam during playback
  // user pan/zoom on top of the fitted view
  const view = useRef({ k: 1, tx: 0, ty: 0 });
  const dragging = useRef<{ x: number; y: number } | null>(null);
  // playback
  const [playing, setPlaying] = useState(false);
  const [rate, setRate] = useState(1);
  const [clock, setClock] = useState(0);
  const rafRef = useRef(0);
  const lastTs = useRef(0);

  const tA = cmp.lap.lap_time;
  const tB = cmp.ref.lap_time;
  const duration = useMemo(
    () => Math.max(tA[tA.length - 1] ?? 0, solo ? 0 : tB[tB.length - 1] ?? 0),
    [tA, tB, solo]
  );
  const step = cmp.dist.length > 1 ? cmp.dist[1] - cmp.dist[0] : 4;

  // playback loop
  useEffect(() => {
    if (!playing) return;
    lastTs.current = performance.now();
    const loop = (ts: number) => {
      const dt = ((ts - lastTs.current) / 1000) * rate;
      lastTs.current = ts;
      setClock((c) => {
        const next = c + dt;
        if (next >= duration) {
          setPlaying(false);
          return duration;
        }
        return next;
      });
      rafRef.current = requestAnimationFrame(loop);
    };
    rafRef.current = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(rafRef.current);
  }, [playing, rate, duration]);

  const resetView = useCallback(() => {
    view.current = { k: 1, tx: 0, ty: 0 };
  }, []);

  // ---- drawing ------------------------------------------------------
  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const dpr = window.devicePixelRatio || 1;
    const cssW = canvas.clientWidth;
    const cssH = canvas.clientHeight || 360;
    if (canvas.width !== cssW * dpr) canvas.width = cssW * dpr;
    if (canvas.height !== cssH * dpr) canvas.height = cssH * dpr;
    const ctx = canvas.getContext("2d")!;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, cssW, cssH);

    const { x, z } = cmp.map;
    const you_x = cmp.map.you_x ?? x;
    const you_z = cmp.map.you_z ?? z;
    if (x.length < 2) return;

    // window (corner selection)
    let i0 = 0, i1 = x.length - 1;
    const corner = insights?.corners.find((c) => c.n === cornerN);
    if (corner) {
      const apexIdx = Math.round(corner.apex_dist / step);
      const span = Math.round(250 / step);
      i0 = Math.max(apexIdx - span, 0);
      i1 = Math.min(apexIdx + span, x.length - 1);
    }

    // fit transform
    let minX = Infinity, maxX = -Infinity, minZ = Infinity, maxZ = -Infinity;
    for (let i = i0; i <= i1; i++) {
      minX = Math.min(minX, x[i], you_x[i]);
      maxX = Math.max(maxX, x[i], you_x[i]);
      minZ = Math.min(minZ, z[i], you_z[i]);
      maxZ = Math.max(maxZ, z[i], you_z[i]);
    }
    const pad = 26;
    let fit = Math.min(
      (cssW - pad * 2) / Math.max(maxX - minX, 1),
      (cssH - pad * 2) / Math.max(maxZ - minZ, 1)
    );
    let ox = (cssW - (maxX - minX) * fit) / 2;
    let oz = (cssH - (maxZ - minZ) * fit) / 2;

    // world position of a car at the playback clock
    const step2 = step;
    const carWorld = (xs: number[], zs: number[], times: number[]) => {
      const d = distAt(clock, times, cmp.dist);
      const fi = Math.min(d / step2, xs.length - 1.001);
      const i = Math.floor(fi);
      const f = fi - i;
      return [xs[i] + (xs[i + 1] - xs[i]) * f, zs[i] + (zs[i + 1] - zs[i]) * f];
    };

    // follow cam: fixed ~170 m frame centered between the two cars
    const followActive = follow && clock > 0;
    if (followActive) {
      const [ax, az] = carWorld(you_x, you_z, tA);
      const [bx, bz] = solo ? [ax, az] : carWorld(x, z, tB);
      fit = Math.min(cssW, cssH) / 170;
      ox = cssW / 2 - ((ax + bx) / 2 - minX) * fit;
      oz = cssH / 2 - (maxZ - (az + bz) / 2) * fit;
    }

    const { k, tx, ty } = view.current;
    const PX = (v: number) => (ox + (v - minX) * fit) * k + tx;
    const PZ = (v: number) => (oz + (maxZ - v) * fit) * k + ty;
    const pxPerM = fit * k;
    if (followActive) {
      i0 = 0;
      i1 = x.length - 1; // draw the whole lap; the camera does the cropping
    }

    // track corridor. Preferred: empirical edges traced from every lap ever
    // driven here (union of legal road actually used). Fallback for sparse
    // tracks: a width band stroked along the reference line.
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    const { el_x, el_z, er_x, er_z } = cmp.map;
    if (el_x && el_z && er_x && er_z) {
      ctx.fillStyle = "rgba(139, 148, 158, 0.13)";
      ctx.beginPath();
      ctx.moveTo(PX(el_x[i0]), PZ(el_z[i0]));
      for (let i = i0 + 1; i <= i1; i++) ctx.lineTo(PX(el_x[i]), PZ(el_z[i]));
      for (let i = i1; i >= i0; i--) ctx.lineTo(PX(er_x[i]), PZ(er_z[i]));
      ctx.closePath();
      ctx.fill();
      ctx.strokeStyle = "rgba(139, 148, 158, 0.35)";
      ctx.lineWidth = 1;
      for (const [ex, ez] of [[el_x, el_z], [er_x, er_z]] as const) {
        ctx.beginPath();
        ctx.moveTo(PX(ex[i0]), PZ(ez[i0]));
        for (let i = i0 + 1; i <= i1; i++) ctx.lineTo(PX(ex[i]), PZ(ez[i]));
        ctx.stroke();
      }
    } else {
      const widths = cmp.map.width;
      ctx.strokeStyle = "rgba(139, 148, 158, 0.16)";
      const chunk = 40;
      for (let s = i0; s < i1; s += chunk) {
        const e = Math.min(s + chunk, i1);
        const w = widths ? widths[Math.min(s + chunk / 2, widths.length - 1)] : 11;
        ctx.lineWidth = Math.max(w * pxPerM, 3);
        ctx.beginPath();
        ctx.moveTo(PX(x[s]), PZ(z[s]));
        for (let i = s + 1; i <= e; i++) ctx.lineTo(PX(x[i]), PZ(z[i]));
        ctx.stroke();
      }
    }

    const line = (xs: number[], zs: number[], color: string, width: number) => {
      ctx.strokeStyle = color;
      ctx.lineWidth = width;
      ctx.beginPath();
      ctx.moveTo(PX(xs[i0]), PZ(zs[i0]));
      for (let i = i0 + 1; i <= i1; i++) ctx.lineTo(PX(xs[i]), PZ(zs[i]));
      ctx.stroke();
    };
    if (!solo) line(x, z, "rgba(255, 138, 61, 0.85)", 1.4);
    line(you_x, you_z, "rgba(77, 208, 225, 0.9)", 1.4);

    // corner labels
    if (insights && !corner) {
      ctx.font = "600 10px 'JetBrains Mono'";
      ctx.fillStyle = "rgba(212,160,23,0.9)";
      for (const c of insights.corners) {
        const i = Math.min(Math.round(c.apex_dist / step), x.length - 1);
        ctx.fillText(officialLabel(c.name, c.n), PX(x[i]) + 6, PZ(z[i]) - 6);
      }
    }

    // playback ghosts
    const dot = (xs: number[], zs: number[], times: number[], color: string) => {
      const d = distAt(clock, times, cmp.dist);
      const fi = d / step;
      const i = Math.min(Math.floor(fi), xs.length - 2);
      const f = fi - i;
      const cx = xs[i] + (xs[i + 1] - xs[i]) * f;
      const cz = zs[i] + (zs[i + 1] - zs[i]) * f;
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.arc(PX(cx), PZ(cz), 5.5, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = "#0e1114";
      ctx.lineWidth = 2;
      ctx.stroke();
    };
    if (clock > 0 || playing) {
      if (!solo) dot(x, z, tB, "#ff8a3d");
      dot(you_x, you_z, tA, "#4dd0e1");
    }
  }, [cmp, insights, cornerN, clock, playing, solo, step]);

  useEffect(() => draw(), [draw]);

  // ---- canvas interactions -----------------------------------------
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const rect = canvas.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      const f = e.deltaY < 0 ? 1.2 : 1 / 1.2;
      const v = view.current;
      const nk = Math.min(Math.max(v.k * f, 1), 60);
      const real = nk / v.k;
      v.tx = mx - (mx - v.tx) * real;
      v.ty = my - (my - v.ty) * real;
      v.k = nk;
      if (v.k === 1) { v.tx = 0; v.ty = 0; }
      draw();
    };
    const onDown = (e: MouseEvent) => { dragging.current = { x: e.clientX, y: e.clientY }; };
    const onMove = (e: MouseEvent) => {
      if (!dragging.current) return;
      view.current.tx += e.clientX - dragging.current.x;
      view.current.ty += e.clientY - dragging.current.y;
      dragging.current = { x: e.clientX, y: e.clientY };
      draw();
    };
    const onUp = () => { dragging.current = null; };
    const onDbl = () => { resetView(); draw(); };
    canvas.addEventListener("wheel", onWheel, { passive: false });
    canvas.addEventListener("mousedown", onDown);
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    canvas.addEventListener("dblclick", onDbl);
    return () => {
      canvas.removeEventListener("wheel", onWheel);
      canvas.removeEventListener("mousedown", onDown);
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
      canvas.removeEventListener("dblclick", onDbl);
    };
  }, [draw, resetView]);

  // readouts at the playback clock
  const idxA = Math.min(Math.round(distAt(clock, tA, cmp.dist) / step), cmp.dist.length - 1);
  const idxB = Math.min(Math.round(distAt(clock, tB, cmp.dist) / step), cmp.dist.length - 1);
  const liveDelta = cmp.delta[idxA] ?? 0;

  return (
    <div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginBottom: 8 }}>
        <button
          className={`toggle ${cornerN == null ? "on" : ""}`}
          onClick={() => { setCornerN(null); resetView(); }}
        >
          FULL TRACK
        </button>
        {insights?.corners.map((c) => (
          <button
            key={c.n}
            className={`toggle ${cornerN === c.n ? "on" : ""}`}
            title={c.name || `corner ${c.n}`}
            onClick={() => { setCornerN(c.n); resetView(); }}
          >
            {officialLabel(c.name, c.n)}
          </button>
        ))}
      </div>

      <canvas ref={canvasRef} style={{ width: "100%", height: 360, cursor: "grab" }} />

      <div className="playbar">
        <button className="play-btn" onClick={() => {
          if (clock >= duration) setClock(0);
          setPlaying(!playing);
        }}>
          {playing ? "❚❚" : "▶"}
        </button>
        <button className={`toggle ${follow ? "on" : ""}`} onClick={() => setFollow(!follow)} title="Chase cam: camera tracks the cars during playback">
          FOLLOW
        </button>
        <select className="rate-select" value={rate} onChange={(e) => setRate(Number(e.target.value))}>
          <option value={0.5}>0.5×</option>
          <option value={1}>1×</option>
          <option value={2}>2×</option>
          <option value={4}>4×</option>
        </select>
        <input
          type="range"
          min={0}
          max={duration || 1}
          step={0.05}
          value={clock}
          onChange={(e) => { setPlaying(false); setClock(Number(e.target.value)); }}
        />
        <span className="play-clock">{fmtTime(clock)}</span>
      </div>

      <div className="play-readout">
        <span style={{ color: "var(--you)" }}>
          A {Math.round((cmp.lap.speed[idxA] ?? 0) * 3.6)} km/h
        </span>
        {!solo && (
          <>
            <span style={{ color: "var(--ref)" }}>
              R {Math.round((cmp.ref.speed[idxB] ?? 0) * 3.6)} km/h
            </span>
            <span className={liveDelta >= 0 ? "loss" : "gain"}>
              {liveDelta >= 0 ? "+" : ""}{liveDelta.toFixed(2)}s
            </span>
          </>
        )}
        <span className="hint" style={{ marginLeft: "auto" }}>
          scroll zoom · drag pan · dbl-click reset · gray band ≈ track width
        </span>
      </div>
    </div>
  );
}
