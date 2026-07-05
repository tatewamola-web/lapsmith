import { useCallback, useEffect, useRef, useState } from "react";
import {
  ComparePayload,
  LapMeta,
  LiveFrame,
  Status,
  fmtTime,
  getCompare,
  getLaps,
  getStatus,
  openLive,
} from "./api";
import LapList from "./components/LapList";
import LiveStrip from "./components/LiveStrip";
import TrackMap from "./components/TrackMap";
import { DeltaChart, PedalChart, SpeedChart, SteeringChart } from "./components/Charts";

export default function App() {
  const [status, setStatus] = useState<Status | null>(null);
  const [laps, setLaps] = useState<LapMeta[]>([]);
  const [youId, setYouId] = useState<number | null>(null);
  const [refId, setRefId] = useState<number | null>(null);
  const [cmp, setCmp] = useState<ComparePayload | null>(null);
  const [frame, setFrame] = useState<LiveFrame | null>(null);
  const autoPicked = useRef(false);

  // status + lap list poll
  useEffect(() => {
    let stop = false;
    const tick = async () => {
      try {
        const [s, l] = await Promise.all([getStatus(), getLaps()]);
        if (stop) return;
        setStatus(s);
        setLaps(l);
        // First data arrival: auto-select latest valid lap vs PB.
        if (!autoPicked.current && l.length > 0) {
          const valid = l.filter((x) => x.valid);
          if (valid.length >= 2) {
            const pb = valid.find((x) => x.is_pb) ?? valid[valid.length - 1];
            const latest = valid.find((x) => x.id !== pb.id) ?? valid[0];
            setYouId(latest.id);
            setRefId(pb.id);
            autoPicked.current = true;
          }
        }
      } catch {
        if (!stop) setStatus(null);
      }
    };
    tick();
    const h = setInterval(tick, 3000);
    return () => {
      stop = true;
      clearInterval(h);
    };
  }, []);

  // live telemetry
  useEffect(() => openLive(setFrame), []);

  // comparison fetch
  useEffect(() => {
    if (youId == null || refId == null || youId === refId) {
      setCmp(null);
      return;
    }
    let stale = false;
    getCompare(youId, refId)
      .then((c) => !stale && setCmp(c))
      .catch(() => !stale && setCmp(null));
    return () => {
      stale = true;
    };
  }, [youId, refId]);

  const onPick = useCallback((id: number, slot: "you" | "ref") => {
    autoPicked.current = true;
    if (slot === "you") setYouId((cur) => (cur === id ? null : id));
    else setRefId((cur) => (cur === id ? null : id));
  }, []);

  const session = status?.session;
  const finalDelta = cmp ? cmp.delta[cmp.delta.length - 1] : null;

  return (
    <div className="app">
      <header className="header">
        <span className="brand">APEX</span>
        {session && session.track && (
          <span className="session">
            <span><b>{session.track}</b></span>
            <span>{session.car}</span>
            <span>{session.session_type}</span>
          </span>
        )}
        <div className={`status-dot ${status?.live ? "live" : ""}`} />
        <span className="status-label">
          {status?.live ? `LIVE · ${status.adapter}` : status?.connected ? "connected" : "offline"}
        </span>
      </header>

      <div className="main">
        <aside className="sidebar">
          <LiveStrip frame={frame} />
          <LapList laps={laps} youId={youId} refId={refId} onPick={onPick} />
        </aside>

        <main className="content">
          {cmp ? (
            <>
              <div className="compare-head">
                <span className="you">
                  LAP {cmp.lap_meta.lap_number} · {fmtTime(cmp.lap_meta.lap_time)}
                </span>
                <span className="vs">vs</span>
                <span className="ref">
                  {cmp.ref_meta.is_pb ? "PB · " : ""}LAP {cmp.ref_meta.lap_number} ·{" "}
                  {fmtTime(cmp.ref_meta.lap_time)}
                </span>
                {finalDelta != null && (
                  <span className={`final-delta ${finalDelta >= 0 ? "pos" : "neg"}`}>
                    {finalDelta >= 0 ? "+" : ""}
                    {finalDelta.toFixed(3)}s
                  </span>
                )}
              </div>

              <div className="grid-2col">
                <div>
                  <div className="panel">
                    <h3>Time Delta</h3>
                    <DeltaChart cmp={cmp} />
                  </div>
                  <div className="panel">
                    <h3>Speed</h3>
                    <SpeedChart cmp={cmp} />
                  </div>
                  <div className="panel">
                    <h3>Throttle / Brake</h3>
                    <PedalChart cmp={cmp} />
                  </div>
                  <div className="panel">
                    <h3>Steering</h3>
                    <SteeringChart cmp={cmp} />
                  </div>
                </div>
                <div>
                  <div className="panel">
                    <h3>Track · time gain/loss</h3>
                    <TrackMap cmp={cmp} />
                  </div>
                  <div className="panel">
                    <h3>Legend</h3>
                    <div style={{ fontSize: 12.5, color: "var(--text-dim)", lineHeight: 1.9 }}>
                      <div><span style={{ color: "var(--you)" }}>━</span> your lap (A)</div>
                      <div><span style={{ color: "var(--ref)" }}>━</span> reference lap (R)</div>
                      <div><span style={{ color: "var(--loss)" }}>━</span> losing time</div>
                      <div><span style={{ color: "var(--gain)" }}>━</span> gaining time</div>
                    </div>
                  </div>
                </div>
              </div>
            </>
          ) : (
            <div className="placeholder">
              {laps.length === 0
                ? "No laps recorded yet. Drive — laps appear here as you complete them."
                : "Pick a lap to analyze (A) and a reference lap (R) from the list."}
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
