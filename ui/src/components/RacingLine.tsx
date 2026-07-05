// Top-down racing-line comparison: your driven line (cyan) over the
// reference line (orange). Full track by default; pick a corner to zoom
// into it and see exactly where the two lines diverge.

import { useEffect, useRef, useState } from "react";
import type { ComparePayload, Insights } from "../api";

interface Props {
  cmp: ComparePayload;
  insights: Insights | null;
}

function officialLabel(name: string, n: number): string {
  return name ? name.split(" ")[0] : `T${n}`;
}

export default function RacingLine({ cmp, insights }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [cornerN, setCornerN] = useState<number | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const dpr = window.devicePixelRatio || 1;
    const cssW = canvas.clientWidth;
    const cssH = 320;
    canvas.width = cssW * dpr;
    canvas.height = cssH * dpr;
    const ctx = canvas.getContext("2d")!;
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, cssW, cssH);

    const { x, z } = cmp.map;
    const you_x = cmp.map.you_x;
    const you_z = cmp.map.you_z;
    if (!you_x || !you_z || x.length < 2) return;

    // window: full lap, or apex ± 250 m for the selected corner
    const step = cmp.dist.length > 1 ? cmp.dist[1] - cmp.dist[0] : 4;
    let i0 = 0;
    let i1 = x.length - 1;
    const corner = insights?.corners.find((c) => c.n === cornerN);
    if (corner) {
      const apexIdx = Math.round(corner.apex_dist / step);
      const span = Math.round(250 / step);
      i0 = Math.max(apexIdx - span, 0);
      i1 = Math.min(apexIdx + span, x.length - 1);
    }

    let minX = Infinity, maxX = -Infinity, minZ = Infinity, maxZ = -Infinity;
    for (let i = i0; i <= i1; i++) {
      for (const [px_, pz_] of [[x[i], z[i]], [you_x[i], you_z[i]]]) {
        if (px_ < minX) minX = px_;
        if (px_ > maxX) maxX = px_;
        if (pz_ < minZ) minZ = pz_;
        if (pz_ > maxZ) maxZ = pz_;
      }
    }
    const pad = 22;
    const scale = Math.min(
      (cssW - pad * 2) / Math.max(maxX - minX, 1),
      (cssH - pad * 2) / Math.max(maxZ - minZ, 1)
    );
    const ox = (cssW - (maxX - minX) * scale) / 2;
    const oz = (cssH - (maxZ - minZ) * scale) / 2;
    const PX = (v: number) => ox + (v - minX) * scale;
    const PZ = (v: number) => oz + (maxZ - v) * scale; // flip: canvas y grows down

    const drawLine = (xs: number[], zs: number[], color: string, width: number) => {
      ctx.strokeStyle = color;
      ctx.lineWidth = width;
      ctx.lineJoin = "round";
      ctx.beginPath();
      ctx.moveTo(PX(xs[i0]), PZ(zs[i0]));
      for (let i = i0 + 1; i <= i1; i++) ctx.lineTo(PX(xs[i]), PZ(zs[i]));
      ctx.stroke();
    };

    drawLine(x, z, "rgba(255, 138, 61, 0.9)", corner ? 3 : 2);      // reference
    drawLine(you_x, you_z, "rgba(77, 208, 225, 0.9)", corner ? 3 : 2); // you

    // direction arrow at the window start (zoomed view only)
    if (corner) {
      const ax = PX(x[i0]), az = PZ(z[i0]);
      const bx = PX(x[Math.min(i0 + 4, i1)]), bz = PZ(z[Math.min(i0 + 4, i1)]);
      const ang = Math.atan2(bz - az, bx - ax);
      ctx.fillStyle = "#8b949e";
      ctx.save();
      ctx.translate(ax, az);
      ctx.rotate(ang);
      ctx.beginPath();
      ctx.moveTo(8, 0); ctx.lineTo(-4, -5); ctx.lineTo(-4, 5);
      ctx.closePath();
      ctx.fill();
      ctx.restore();
    }

    // corner markers (full-track view)
    if (!corner && insights) {
      ctx.font = "600 10px 'JetBrains Mono'";
      ctx.fillStyle = "rgba(212,160,23,0.9)";
      for (const c of insights.corners) {
        const i = Math.min(Math.round(c.apex_dist / step), x.length - 1);
        ctx.fillText(officialLabel(c.name, c.n), PX(x[i]) + 6, PZ(z[i]) - 6);
      }
    }
  }, [cmp, insights, cornerN]);

  return (
    <div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginBottom: 8 }}>
        <button className={`toggle ${cornerN == null ? "on" : ""}`} onClick={() => setCornerN(null)}>
          FULL TRACK
        </button>
        {insights?.corners.map((c) => (
          <button
            key={c.n}
            className={`toggle ${cornerN === c.n ? "on" : ""}`}
            title={c.name || `corner ${c.n}`}
            onClick={() => setCornerN(c.n)}
          >
            {officialLabel(c.name, c.n)}
          </button>
        ))}
      </div>
      <canvas ref={canvasRef} style={{ width: "100%", height: 320 }} />
    </div>
  );
}
