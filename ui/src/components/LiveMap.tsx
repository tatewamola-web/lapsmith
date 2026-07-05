// Live track map: the racing line from your PB lap (gray), your recent
// trail (cyan, fading), and a bright dot for the car right now.

import { useEffect, useRef } from "react";
import type { LapChannels, LiveFrame } from "../api";

const TRAIL_MAX = 1500; // ~60s of frames

interface Props {
  frame: LiveFrame | null;
  refLine: LapChannels | null; // PB lap of current track/car, if any
}

export default function LiveMap({ frame, refLine }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const trail = useRef<[number, number][]>([]);
  const bounds = useRef({ minX: Infinity, maxX: -Infinity, minZ: Infinity, maxZ: -Infinity });

  // reset trail when the reference line changes (new track)
  useEffect(() => {
    trail.current = [];
    bounds.current = { minX: Infinity, maxX: -Infinity, minZ: Infinity, maxZ: -Infinity };
  }, [refLine]);

  useEffect(() => {
    if (frame) {
      trail.current.push([frame.pos_x, frame.pos_z]);
      if (trail.current.length > TRAIL_MAX) trail.current.shift();
    }

    const canvas = canvasRef.current;
    if (!canvas) return;
    const dpr = window.devicePixelRatio || 1;
    const cssW = canvas.clientWidth;
    const cssH = canvas.clientHeight || 380;
    canvas.width = cssW * dpr;
    canvas.height = cssH * dpr;
    const ctx = canvas.getContext("2d")!;
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, cssW, cssH);

    // establish bounds from ref line, else from what we've seen
    const b = bounds.current;
    const feed = (x: number, z: number) => {
      if (x < b.minX) b.minX = x;
      if (x > b.maxX) b.maxX = x;
      if (z < b.minZ) b.minZ = z;
      if (z > b.maxZ) b.maxZ = z;
    };
    if (refLine) for (let i = 0; i < refLine.pos_x.length; i++) feed(refLine.pos_x[i], refLine.pos_z[i]);
    for (const [x, z] of trail.current) feed(x, z);
    if (!isFinite(b.minX) || b.maxX - b.minX < 1) {
      ctx.fillStyle = "#58626e";
      ctx.font = "12px Inter";
      ctx.textAlign = "center";
      ctx.fillText("waiting for track data…", cssW / 2, cssH / 2);
      return;
    }

    const pad = 20;
    const scale = Math.min(
      (cssW - pad * 2) / Math.max(b.maxX - b.minX, 1),
      (cssH - pad * 2) / Math.max(b.maxZ - b.minZ, 1)
    );
    const ox = (cssW - (b.maxX - b.minX) * scale) / 2;
    const oz = (cssH - (b.maxZ - b.minZ) * scale) / 2;
    const px = (x: number) => ox + (x - b.minX) * scale;
    // canvas y grows downward; flip z so the circuit isn't mirrored
    const pz = (z: number) => oz + (b.maxZ - z) * scale;

    // racing line (PB lap)
    if (refLine && refLine.pos_x.length > 1) {
      ctx.strokeStyle = "rgba(139, 148, 158, 0.45)";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(px(refLine.pos_x[0]), pz(refLine.pos_z[0]));
      for (let i = 1; i < refLine.pos_x.length; i++) {
        ctx.lineTo(px(refLine.pos_x[i]), pz(refLine.pos_z[i]));
      }
      ctx.stroke();
      // start/finish
      ctx.fillStyle = "#e8eaed";
      ctx.beginPath();
      ctx.arc(px(refLine.pos_x[0]), pz(refLine.pos_z[0]), 3.5, 0, Math.PI * 2);
      ctx.fill();
    }

    // live trail, fading out toward the tail
    const t = trail.current;
    for (let i = 1; i < t.length; i++) {
      const a = (i / t.length) * 0.85;
      ctx.strokeStyle = `rgba(77, 208, 225, ${a.toFixed(3)})`;
      ctx.lineWidth = 2.5;
      ctx.beginPath();
      ctx.moveTo(px(t[i - 1][0]), pz(t[i - 1][1]));
      ctx.lineTo(px(t[i][0]), pz(t[i][1]));
      ctx.stroke();
    }

    // the car
    if (t.length > 0) {
      const [cx, cz] = t[t.length - 1];
      ctx.fillStyle = "#4dd0e1";
      ctx.beginPath();
      ctx.arc(px(cx), pz(cz), 6, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = "#0e1114";
      ctx.lineWidth = 2;
      ctx.stroke();
    }
  }, [frame, refLine]);

  return <canvas ref={canvasRef} style={{ width: "100%", height: 380 }} />;
}
