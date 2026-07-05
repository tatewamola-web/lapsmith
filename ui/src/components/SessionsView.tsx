// Session browser, grouped by track: every stint you've driven, with each
// track's all-time best and most recent activity up front.

import type { SessionMeta } from "../api";
import { fmtDate, fmtTime } from "../api";

interface Props {
  sessions: SessionMeta[];
  onOpen: (id: number) => void;
}

interface TrackGroup {
  track: string;
  sessions: SessionMeta[];
  best: number | null;
  lastDriven: string;
}

export default function SessionsView({ sessions, onOpen }: Props) {
  if (sessions.length === 0) {
    return <div className="placeholder">No sessions yet — drive some laps and they'll appear here.</div>;
  }

  const groups = new Map<string, TrackGroup>();
  for (const s of sessions) {
    const key = s.track || "Unknown track";
    let g = groups.get(key);
    if (!g) {
      g = { track: key, sessions: [], best: null, lastDriven: s.started_at };
      groups.set(key, g);
    }
    g.sessions.push(s);
    if (s.best_lap != null && (g.best == null || s.best_lap < g.best)) g.best = s.best_lap;
    if (s.started_at > g.lastDriven) g.lastDriven = s.started_at;
  }
  const ordered = [...groups.values()].sort((a, b) => (a.lastDriven < b.lastDriven ? 1 : -1));

  return (
    <div className="sessions-wrap">
      {ordered.map((g) => (
        <section key={g.track} className="track-group">
          <div className="track-group-head">
            <b>{g.track}</b>
            <span className="meta">
              {g.sessions.length} session{g.sessions.length !== 1 ? "s" : ""} · last {fmtDate(g.lastDriven)}
            </span>
            <span className="best">
              best <b>{fmtTime(g.best)}</b>
            </span>
          </div>
          {g.sessions.map((s) => (
            <div className="session-card" key={s.id} onClick={() => onOpen(s.id)} style={{ cursor: "pointer" }}>
              <div className="when">{fmtDate(s.started_at)}</div>
              <div className="where">
                <b className={`stype ${s.session_type || ""}`}>{(s.session_type || "session").toUpperCase()}</b>
                <span>
                  {s.car}
                  {s.source === "game-log" ? " · from game log" : ""}
                </span>
              </div>
              <div className="stat">
                laps
                <b>
                  {s.valid_laps}/{s.laps}
                </b>
              </div>
              <div className="stat">
                best
                <b className={s.best_lap != null && s.best_lap === g.best ? "gold" : ""}>{fmtTime(s.best_lap)}</b>
              </div>
              <button className="pick" onClick={(e) => { e.stopPropagation(); onOpen(s.id); }}>
                ANALYZE →
              </button>
            </div>
          ))}
        </section>
      ))}
    </div>
  );
}
