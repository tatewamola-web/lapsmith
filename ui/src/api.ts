// Typed client for the engine's REST + WebSocket API.

export interface LapMeta {
  id: number;
  created_at: string;
  game: string;
  track: string;
  car: string;
  session_type: string;
  lap_number: number;
  lap_time: number;
  s1: number | null;
  s2: number | null;
  s3: number | null;
  valid: number;
  source: string;
  driver: string;
  is_pb: boolean;
}

export interface ChannelSet {
  speed: number[];
  throttle: number[];
  brake: number[];
  steering: number[];
  gear: number[];
}

export interface ComparePayload {
  dist: number[];
  delta: number[];
  lap: ChannelSet;
  ref: ChannelSet;
  map: { x: number[]; z: number[] };
  lap_meta: LapMeta;
  ref_meta: LapMeta;
}

export interface LiveFrame {
  timestamp: number;
  lap_number: number;
  lap_time: number;
  lap_dist: number;
  speed: number;
  throttle: number;
  brake: number;
  steering: number;
  gear: number;
  rpm: number;
  last_lap_time: number;
  best_lap_time: number;
}

export interface Status {
  adapter: string;
  connected: boolean;
  live: boolean;
  session: { game: string; track: string; car: string; track_length: number; session_type: string };
  laps_recorded: number;
}

export async function getStatus(): Promise<Status> {
  return (await fetch("/api/status")).json();
}

export async function getLaps(): Promise<LapMeta[]> {
  return (await fetch("/api/laps")).json();
}

export async function getCompare(lap: number, ref: number): Promise<ComparePayload> {
  const r = await fetch(`/api/compare?lap=${lap}&ref=${ref}`);
  if (!r.ok) throw new Error(`compare failed: ${r.status}`);
  return r.json();
}

export function openLive(onFrame: (frame: LiveFrame) => void): () => void {
  let ws: WebSocket | null = null;
  let closed = false;

  const connect = () => {
    if (closed) return;
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}/ws/live`);
    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.type === "frame") onFrame(msg.frame);
    };
    ws.onclose = () => {
      if (!closed) setTimeout(connect, 2000);
    };
  };
  connect();
  return () => {
    closed = true;
    ws?.close();
  };
}

export function fmtTime(t: number | null | undefined): string {
  if (t == null || t <= 0) return "–";
  const m = Math.floor(t / 60);
  const s = t - m * 60;
  return m > 0 ? `${m}:${s.toFixed(3).padStart(6, "0")}` : s.toFixed(3);
}
