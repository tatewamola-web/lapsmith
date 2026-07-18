// Track map drawn from the reference lap's world position, with each
// segment colored by the local rate of time loss/gain. Green stretch =
// you're faster there; red = the reference is taking time out of you.

import { useEffect, useRef } from "react";
import type { ComparePayload, Insights } from "../api";

export default function TrackMap({ cmp, insights, hoverPct }: {
  cmp: ComparePayload;
  insights?: Insights | null;
  hoverPct?: number | null;
}) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const dpr = window.devicePixelRatio || 1;
    const cssW = canvas.clientWidth;
    const cssH = 300;
    canvas.width = cssW * dpr;
    canvas.height = cssH * dpr;
    const ctx = canvas.getContext("2d")!;
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, cssW, cssH);

    const { x, z } = cmp.map;
    if (x.length < 2) return;

    const minX = Math.min(...x), maxX = Math.max(...x);
    const minZ = Math.min(...z), maxZ = Math.max(...z);
    const pad = 18;
    const scale = Math.min(
      (cssW - pad * 2) / Math.max(maxX - minX, 1),
      (cssH - pad * 2) / Math.max(maxZ - minZ, 1)
    );
    const ox = (cssW - (maxX - minX) * scale) / 2;
    const oz = (cssH - (maxZ - minZ) * scale) / 2;
    const px = (i: number) => ox + (x[i] - minX) * scale;
    // canvas y grows downward; flip z so the circuit isn't mirrored
    const pz = (i: number) => oz + (maxZ - z[i]) * scale;

    // Local time-loss rate: slope of delta over ~40 m windows.
    const win = 10;
    const slope = (i: number) => {
      const a = Math.max(i - win, 0);
      const b = Math.min(i + win, cmp.delta.length - 1);
      const dd = cmp.dist[b] - cmp.dist[a] || 1;
      return (cmp.delta[b] - cmp.delta[a]) / dd; // s per meter
    };
    // normalize color intensity to the lap's own worst sections
    let maxAbs = 1e-6;
    for (let i = 0; i < cmp.delta.length; i += 4) maxAbs = Math.max(maxAbs, Math.abs(slope(i)));

    ctx.lineWidth = 3.5;
    ctx.lineCap = "round";
    for (let i = 1; i < x.length; i++) {
      const s = slope(i) / maxAbs; // -1..1
      const mag = Math.min(Math.abs(s), 1);
      ctx.strokeStyle =
        s > 0
          ? `rgba(248, 81, 73, ${0.25 + 0.75 * mag})`
          : `rgba(63, 185, 80, ${0.25 + 0.75 * mag})`;
      ctx.beginPath();
      ctx.moveTo(px(i - 1), pz(i - 1));
      ctx.lineTo(px(i), pz(i));
      ctx.stroke();
    }

    // start/finish marker
    ctx.fillStyle = "#e8eaed";
    ctx.beginPath();
    ctx.arc(px(0), pz(0), 4, 0, Math.PI * 2);
    ctx.fill();
    ctx.font = "10px 'JetBrains Mono'";
    ctx.fillStyle = "#8b949e";
    ctx.fillText("S/F", px(0) + 7, pz(0) + 3);

    // chart-hover position mirrored onto the map
    if (hoverPct != null) {
      const hi = Math.min(Math.round((hoverPct / 100) * (x.length - 1)), x.length - 1);
      ctx.fillStyle = "#ffffff";
      ctx.beginPath();
      ctx.arc(px(hi), pz(hi), 5, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = "#0e1114";
      ctx.lineWidth = 2;
      ctx.stroke();
    }

    // corner labels from the insights engine (same distance grid as cmp)
    if (insights) {
      const step = cmp.dist.length > 1 ? cmp.dist[1] - cmp.dist[0] : 4;
      ctx.font = "600 10px 'JetBrains Mono'";
      for (const c of insights.corners) {
        const i = Math.min(Math.round(c.apex_dist / step), x.length - 1);
        const cxp = px(i), czp = pz(i);
        ctx.fillStyle = "#d4a017";
        ctx.beginPath();
        ctx.arc(cxp, czp, 2.5, 0, Math.PI * 2);
        ctx.fill();
        // nudge the label away from the racing line
        const j = Math.max(i - 3, 0);
        const nx = cxp - px(j), nz = czp - pz(j);
        const len = Math.hypot(nx, nz) || 1;
        ctx.fillStyle = "rgba(212,160,23,0.95)";
        const label = c.name ? c.name.split(" ")[0] : `T${c.n}`;
        ctx.fillText(label, cxp + (-nz / len) * 12, czp + (nx / len) * 12 + 3);
      }
    }
  }, [cmp, insights, hoverPct]);

  return <canvas ref={ref} style={{ width: "100%", height: 300 }} />;
}
