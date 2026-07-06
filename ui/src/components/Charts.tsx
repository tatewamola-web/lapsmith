// Stacked telemetry charts on a shared distance axis with synced cursors.
// uPlot is used directly (no wrapper lib): it renders 100k points without
// breaking a sweat, which matters once real 50 Hz laps arrive.

import { useEffect, useRef } from "react";
import uPlot from "uplot";
import type { ComparePayload } from "../api";

const SYNC_KEY = uPlot.sync("apex-dist");

const AXIS = {
  stroke: "#58626e",
  grid: { stroke: "rgba(38,45,54,0.6)", width: 1 },
  ticks: { stroke: "#262d36", width: 1 },
  font: "11px 'JetBrains Mono'",
} as const;

function useUplot(
  build: (width: number) => uPlot.Options,
  data: uPlot.AlignedData,
  deps: unknown[]
) {
  const ref = useRef<HTMLDivElement>(null);
  const plotRef = useRef<uPlot | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const make = () => {
      plotRef.current?.destroy();
      const opts = build(el.clientWidth);
      plotRef.current = new uPlot(opts, data, el);
    };
    make();
    const ro = new ResizeObserver(() => {
      const w = el.clientWidth;
      if (plotRef.current && w > 0) plotRef.current.setSize({ width: w, height: plotRef.current.height });
    });
    ro.observe(el);
    return () => {
      ro.disconnect();
      plotRef.current?.destroy();
      plotRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return ref;
}

function baseOpts(width: number, height: number, yLabel: string): uPlot.Options {
  return {
    width,
    height,
    cursor: {
      sync: { key: SYNC_KEY.key, setSeries: false },
      points: { size: 5 },
    },
    legend: { show: false },
    scales: { x: { time: false } },
    axes: [
      // X is % of lap internally (corners align across tracks), but the
      // tick labels add nothing — sector lines and corner markers are the
      // real landmarks, so the axis stays quiet.
      { ...AXIS, size: 8, values: (_u, vs) => vs.map(() => "") },
      { ...AXIS, size: 52, label: yLabel, labelFont: "10px Inter", labelGap: 2 },
    ],
    series: [{}],
  };
}

/** Distance grid → % of lap (0–100). */
function pct(dist: number[]): number[] {
  const max = dist[dist.length - 1] || 1;
  return dist.map((d) => (d / max) * 100);
}

export interface ChartMarkers {
  sectors: { pct: number; label: string }[];
  corners: { pct: number; label: string }[];
}

/** Mouse-wheel zoom on the x axis, centered on the cursor. Double-click still resets. */
function wheelZoomPlugin(): uPlot.Plugin {
  return {
    hooks: {
      ready: (u) => {
        u.over.addEventListener(
          "wheel",
          (e) => {
            e.preventDefault();
            const rect = u.over.getBoundingClientRect();
            const cursorX = e.clientX - rect.left;
            const xVal = u.posToVal(cursorX, "x");
            const xData = u.data[0] as number[];
            const dataMin = xData[0];
            const dataMax = xData[xData.length - 1];
            const curMin = u.scales.x.min ?? dataMin;
            const curMax = u.scales.x.max ?? dataMax;
            const factor = e.deltaY < 0 ? 0.75 : 1 / 0.75;
            let range = (curMax - curMin) * factor;
            range = Math.min(range, dataMax - dataMin);
            let min = xVal - ((cursorX / u.over.clientWidth) || 0.5) * range;
            let max = min + range;
            if (min < dataMin) { min = dataMin; max = min + range; }
            if (max > dataMax) { max = dataMax; min = max - range; }
            u.setScale("x", { min, max });
          },
          { passive: false }
        );
      },
    },
  };
}

/** Sector lines (dashed verticals) and corner labels drawn onto the plot. */
function markersPlugin(markers?: ChartMarkers): uPlot.Plugin {
  return {
    hooks: {
      draw: (u) => {
        if (!markers) return;
        const ctx = u.ctx;
        const dpr = window.devicePixelRatio || 1;
        const inX = (x: number) => x >= u.bbox.left - 1 && x <= u.bbox.left + u.bbox.width + 1;
        ctx.save();
        ctx.font = `${10 * dpr}px 'JetBrains Mono'`;
        ctx.textAlign = "center";
        for (const s of markers.sectors) {
          if (s.pct <= 0) continue;
          const x = u.valToPos(s.pct, "x", true);
          if (!inX(x)) continue;
          ctx.strokeStyle = "rgba(139,148,158,0.4)";
          ctx.setLineDash([4 * dpr, 4 * dpr]);
          ctx.beginPath();
          ctx.moveTo(x, u.bbox.top);
          ctx.lineTo(x, u.bbox.top + u.bbox.height);
          ctx.stroke();
          ctx.setLineDash([]);
          ctx.fillStyle = "rgba(139,148,158,0.9)";
          ctx.fillText(s.label, x, u.bbox.top + 11 * dpr);
        }
        for (const c of markers.corners) {
          const x = u.valToPos(c.pct, "x", true);
          if (!inX(x)) continue;
          ctx.fillStyle = "rgba(212,160,23,0.85)";
          ctx.fillText(c.label, x, u.bbox.top + u.bbox.height - 4 * dpr);
        }
        ctx.restore();
      },
    },
  };
}

export function DeltaChart({ cmp, markers }: { cmp: ComparePayload; markers?: ChartMarkers }) {
  const data: uPlot.AlignedData = [pct(cmp.dist), cmp.delta];
  const ref = useUplot(
    (w) => {
      const o = baseOpts(w, 150, "delta s");
      o.plugins = [wheelZoomPlugin(), markersPlugin(markers)];
      o.series.push({
        stroke: "#e8eaed",
        width: 1.5,
        fill: (u, si) => {
          // red above zero (losing time), green below (gaining)
          const grad = u.ctx.createLinearGradient(0, u.bbox.top, 0, u.bbox.top + u.bbox.height);
          const zero = u.valToPos(0, "y", false) / u.over.clientHeight;
          const z = Math.min(Math.max(zero, 0), 1);
          grad.addColorStop(0, "rgba(248,81,73,0.28)");
          grad.addColorStop(z, "rgba(248,81,73,0.02)");
          grad.addColorStop(z, "rgba(63,185,80,0.02)");
          grad.addColorStop(1, "rgba(63,185,80,0.28)");
          return grad;
        },
      });
      return o;
    },
    data,
    [cmp]
  );
  return <div ref={ref} />;
}

export function SpeedChart({ cmp, markers }: { cmp: ComparePayload; markers?: ChartMarkers }) {
  const kmh = (a: number[]) => a.map((v) => v * 3.6);
  const data: uPlot.AlignedData = [pct(cmp.dist), kmh(cmp.lap.speed), kmh(cmp.ref.speed)];
  const ref = useUplot(
    (w) => {
      const o = baseOpts(w, 200, "km/h");
      o.plugins = [wheelZoomPlugin(), markersPlugin(markers)];
      o.series.push({ stroke: "#4dd0e1", width: 1.5 });
      o.series.push({ stroke: "#ff8a3d", width: 1.5 });
      return o;
    },
    data,
    [cmp]
  );
  return <div ref={ref} />;
}

export function PedalChart({ cmp, markers }: { cmp: ComparePayload; markers?: ChartMarkers }) {
  const p100 = (a: number[]) => a.map((v) => v * 100);
  const data: uPlot.AlignedData = [
    pct(cmp.dist),
    p100(cmp.lap.throttle),
    p100(cmp.ref.throttle),
    p100(cmp.lap.brake),
    p100(cmp.ref.brake),
  ];
  const ref = useUplot(
    (w) => {
      const o = baseOpts(w, 150, "%");
      o.plugins = [wheelZoomPlugin(), markersPlugin(markers)];
      o.series.push({ stroke: "#3fb950", width: 1.5 });
      o.series.push({ stroke: "rgba(63,185,80,0.45)", width: 1.2, dash: [4, 4] });
      o.series.push({ stroke: "#f85149", width: 1.5 });
      o.series.push({ stroke: "rgba(248,81,73,0.45)", width: 1.2, dash: [4, 4] });
      return o;
    },
    data,
    [cmp]
  );
  return <div ref={ref} />;
}

export function SteeringChart({ cmp, markers }: { cmp: ComparePayload; markers?: ChartMarkers }) {
  const data: uPlot.AlignedData = [pct(cmp.dist), cmp.lap.steering, cmp.ref.steering];
  const ref = useUplot(
    (w) => {
      const o = baseOpts(w, 110, "steer");
      o.plugins = [wheelZoomPlugin(), markersPlugin(markers)];
      o.series.push({ stroke: "#4dd0e1", width: 1.2 });
      o.series.push({ stroke: "#ff8a3d", width: 1.2 });
      return o;
    },
    data,
    [cmp]
  );
  return <div ref={ref} />;
}
