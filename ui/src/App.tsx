import { useCallback, useEffect, useRef, useState } from "react";
import {
  ComparePayload,
  LapMeta,
  LiveFrame,
  SessionMeta,
  Status,
  deleteLap,
  getCompare,
  getLaps,
  getSessions,
  getStatus,
  openLive,
} from "./api";
import AnalysisView from "./components/AnalysisView";
import LiveView from "./components/LiveView";
import SessionsView from "./components/SessionsView";

type Tab = "live" | "analysis" | "sessions";

export default function App() {
  const [tab, setTab] = useState<Tab>("analysis");
  const [status, setStatus] = useState<Status | null>(null);
  const [laps, setLaps] = useState<LapMeta[]>([]);
  const [sessions, setSessions] = useState<SessionMeta[]>([]);
  const [sessionFilter, setSessionFilter] = useState<number | null>(null);
  const [youId, setYouId] = useState<number | null>(null);
  const [refId, setRefId] = useState<number | null>(null);
  const [cmp, setCmp] = useState<ComparePayload | null>(null);
  const [frame, setFrame] = useState<LiveFrame | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const autoPicked = useRef(false);

  // status + lap list + sessions poll
  useEffect(() => {
    let stop = false;
    const tick = async () => {
      try {
        const [s, l, ses] = await Promise.all([
          getStatus(),
          getLaps(sessionFilter),
          getSessions(),
        ]);
        if (stop) return;
        setStatus(s);
        setLaps(l);
        setSessions(ses);
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
  }, [sessionFilter]);

  // live telemetry; auto-switch to Live tab when driving starts is left to
  // the user — telemetry keeps flowing regardless of the visible tab.
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

  const onDelete = useCallback(async (id: number) => {
    await deleteLap(id);
    setYouId((cur) => (cur === id ? null : cur));
    setRefId((cur) => (cur === id ? null : cur));
    setLaps((cur) => cur.filter((l) => l.id !== id));
  }, []);

  const openSession = useCallback((id: number) => {
    setSessionFilter(id);
    autoPicked.current = false; // re-auto-pick within this session
    setTab("analysis");
  }, []);

  const session = status?.session;

  return (
    <div className="app">
      <header className="header">
        <span className="brand">APEX</span>
        <nav className="tabs">
          {(["live", "analysis", "sessions"] as Tab[]).map((t) => (
            <button key={t} className={`tab ${tab === t ? "active" : ""}`} onClick={() => setTab(t)}>
              {t.toUpperCase()}
            </button>
          ))}
        </nav>
        {session && session.track && (
          <span className="session">
            <span><b>{session.track}</b></span>
            <span>{session.car}</span>
          </span>
        )}
        <div className="header-right">
          <div className={`status-dot ${status?.live ? "live" : ""}`} />
          <span className="status-label">
            {status?.live ? `LIVE · ${status.adapter}` : status ? "engine idle" : "engine offline"}
          </span>
          <div className="menu-wrap">
            <button className="menu-btn" onClick={() => setMenuOpen(!menuOpen)}>☰</button>
            {menuOpen && (
              <div className="menu-pop" onMouseLeave={() => setMenuOpen(false)}>
                <div className="item"><span>Adapter</span><b>{status?.adapter ?? "–"}</b></div>
                <div className="item"><span>Engine</span><b>{status ? (status.connected ? "connected" : "waiting") : "offline"}</b></div>
                <div className="item"><span>Laps this run</span><b>{status?.laps_recorded ?? 0}</b></div>
                <div className="sep" />
                <div className="item"><span>Data folder</span><b>data\</b></div>
                <div className="item"><span>Version</span><b>0.2.0</b></div>
              </div>
            )}
          </div>
        </div>
      </header>

      <div className="main">
        {tab === "live" && <LiveView frame={frame} status={status} />}
        {tab === "analysis" && (
          <AnalysisView
            laps={laps}
            youId={youId}
            refId={refId}
            cmp={cmp}
            sessionFilter={sessionFilter}
            onPick={onPick}
            onDelete={onDelete}
            onClearFilter={() => setSessionFilter(null)}
          />
        )}
        {tab === "sessions" && <SessionsView sessions={sessions} onOpen={openSession} />}
      </div>
    </div>
  );
}
