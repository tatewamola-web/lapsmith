// Session browser: every stint you've driven, newest first — like the
// session list in SimHub or LMU's replay screen.

import type { SessionMeta } from "../api";
import { fmtDate, fmtTime } from "../api";

interface Props {
  sessions: SessionMeta[];
  onOpen: (id: number) => void;
}

export default function SessionsView({ sessions, onOpen }: Props) {
  if (sessions.length === 0) {
    return <div className="placeholder">No sessions yet — drive some laps and they'll appear here.</div>;
  }
  return (
    <div className="sessions-wrap">
      {sessions.map((s) => (
        <div className="session-card" key={s.id} onClick={() => onOpen(s.id)} style={{ cursor: "pointer" }}>
          <div className="when">{fmtDate(s.started_at)}</div>
          <div className="where">
            <b>{s.track || "Unknown track"}</b>
            <span>
              {s.car} · {s.session_type || "session"} · {s.game}
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
            <b className={s.best_lap != null ? "gold" : ""}>{fmtTime(s.best_lap)}</b>
          </div>
          <button className="pick" onClick={(e) => { e.stopPropagation(); onOpen(s.id); }}>
            ANALYZE →
          </button>
        </div>
      ))}
    </div>
  );
}
