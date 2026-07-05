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
      // X is % of lap: corners land in the same place for every track,
      // and "70% through the lap" reads more naturally than kilometers.
      { ...AXIS, size: 28, values: (_u, vs) => vs.map((v) => `${Math.round(v)}%`) },
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

export function DeltaChart({ cmp }: { cmp: ComparePayload }) {
  const data: uPlot.AlignedData = [pct(cmp.dist), cmp.delta];
  const ref = useUplot(
    (w) => {
      const o = baseOpts(w, 140, "delta s");
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

export function SpeedChart({ cmp }: { cmp: ComparePayload }) {
  const kmh = (a: number[]) => a.map((v) => v * 3.6);
  const data: uPlot.AlignedData = [pct(cmp.dist), kmh(cmp.lap.speed), kmh(cmp.ref.speed)];
  const ref = useUplot(
    (w) => {
      const o = baseOpts(w, 190, "km/h");
      o.series.push({ stroke: "#4dd0e1", width: 1.5 });
      o.series.push({ stroke: "#ff8a3d", width: 1.5 });
      return o;
    },
    data,
    [cmp]
  );
  return <div ref={ref} />;
}

export function PedalChart({ cmp }: { cmp: ComparePayload }) {
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

export function SteeringChart({ cmp }: { cmp: ComparePayload }) {
  const data: uPlot.AlignedData = [pct(cmp.dist), cmp.lap.steering, cmp.ref.steering];
  const ref = useUplot(
    (w) => {
      const o = baseOpts(w, 110, "steer");
      o.series.push({ stroke: "#4dd0e1", width: 1.2 });
      o.series.push({ stroke: "#ff8a3d", width: 1.2 });
      return o;
    },
    data,
    [cmp]
  );
  return <div ref={ref} />;
}
