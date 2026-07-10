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
  car_class?: string;
  is_pb: boolean;
  has_data?: boolean;
}

export interface ChannelSet {
  speed: number[];
  throttle: number[];
  brake: number[];
  steering: number[];
  gear: number[];
  lap_time: number[];
}

export interface ComparePayload {
  dist: number[];
  delta: number[];
  lap: ChannelSet;
  ref: ChannelSet;
  map: {
    x: number[];
    z: number[];
    you_x?: number[];
    you_z?: number[];
    width?: number[];
    el_x?: number[]; // empirical track edges (from all laps ever driven)
    el_z?: number[];
    er_x?: number[];
    er_z?: number[];
  };
  lap_meta: LapMeta;
  ref_meta: LapMeta;
}

export interface LiveFrame {
  timestamp: number;
  lap_number: number;
  lap_time: number;
  lap_dist: number;
  pos_x: number;
  pos_z: number;
  speed: number;
  throttle: number;
  brake: number;
  steering: number;
  gear: number;
  rpm: number;
  last_lap_time: number;
  best_lap_time: number;
}

export interface SessionMeta {
  id: number;
  started_at: string;
  game: string;
  track: string;
  car: string;
  session_type: string;
  source?: string;
  laps: number;
  valid_laps: number;
  best_lap: number | null;
}

export interface LapChannels {
  lap_dist: number[];
  lap_time: number[];
  speed: number[];
  throttle: number[];
  brake: number[];
  steering: number[];
  gear: number[];
  rpm: number[];
  pos_x: number[];
  pos_z: number[];
}

export interface Status {
  adapter: string;
  connected: boolean;
  live: boolean;
  session: { game: string; track: string; car: string; car_class?: string; track_length: number; session_type: string };
  laps_recorded: number;
}

export async function getStatus(): Promise<Status> {
  return (await fetch("/api/status")).json();
}

export async function getLaps(sessionId?: number | null): Promise<LapMeta[]> {
  const q = sessionId ? `?session=${sessionId}` : "";
  return (await fetch(`/api/laps${q}`)).json();
}

export async function getSessions(): Promise<SessionMeta[]> {
  return (await fetch("/api/sessions")).json();
}

export async function getLapData(id: number): Promise<LapChannels> {
  const r = await fetch(`/api/laps/${id}/data`);
  if (!r.ok) throw new Error(`lap data failed: ${r.status}`);
  return r.json();
}

export async function getPB(game: string, track: string, car: string, carClass = ""): Promise<LapMeta | null> {
  const q = new URLSearchParams({ game, track, car, car_class: carClass });
  const r = await fetch(`/api/pb?${q}`);
  return r.ok ? r.json() : null;
}

export async function deleteLap(id: number): Promise<void> {
  await fetch(`/api/laps/${id}`, { method: "DELETE" });
}

export interface CornerInsight {
  n: number;
  name: string;
  apex_dist: number;
  apex_pct: number;
  sector: number;
  loss: number;
  apex_kmh_you: number;
  apex_kmh_ref: number;
  brake_you: number;
  brake_ref: number;
  advice: string;
}

export interface Insights {
  corners: CornerInsight[];
  worst: number[];
  s1_dist: number;
  s2_dist: number;
  total_delta: number;
  corner_loss_total: number;
}

export async function getInsights(lap: number, ref: number): Promise<Insights> {
  const r = await fetch(`/api/insights?lap=${lap}&ref=${ref}`);
  if (!r.ok) throw new Error(`insights failed: ${r.status}`);
  return r.json();
}

export interface IdealLap {
  s1: number;
  s2: number;
  s3: number;
  total: number;
  laps_considered: number;
  pb_time: number | null;
  gap_to_pb: number | null;
}

export async function getIdeal(game: string, track: string, car: string, carClass = ""): Promise<IdealLap | null> {
  const q = new URLSearchParams({ game, track, car, car_class: carClass });
  const r = await fetch(`/api/ideal?${q}`);
  return r.ok ? r.json() : null;
}

export function fmtDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  });
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
