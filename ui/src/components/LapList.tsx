import { useState } from "react";
import type { LapMeta } from "../api";
import { fmtTime } from "../api";

interface Props {
  laps: LapMeta[];
  youId: number | null;
  refId: number | null;
  sessionFilter: number | null;
  onPick: (id: number, slot: "you" | "ref") => void;
  onDelete: (id: number) => void;
  onClearFilter: () => void;
}

export default function LapList({
  laps, youId, refId, sessionFilter, onPick, onDelete, onClearFilter,
}: Props) {
  const [validOnly, setValidOnly] = useState(false);
  const shown = validOnly ? laps.filter((l) => l.valid) : laps;

  return (
    <div>
      <div className="laplist-head">
        <span>
          Laps · {shown.length}
          {sessionFilter != null && (
            <button className="toggle on" style={{ marginLeft: 8 }} onClick={onClearFilter}>
              session #{sessionFilter} ✕
            </button>
          )}
        </span>
        <button className={`toggle ${validOnly ? "on" : ""}`} onClick={() => setValidOnly(!validOnly)}>
          valid only
        </button>
      </div>
      <div className="lap-rows">
        {shown.map((lap) => {
          const sel = youId === lap.id ? "sel-you" : refId === lap.id ? "sel-ref" : "";
          return (
            <div
              key={lap.id}
              className={`lap-row ${lap.valid ? "" : "invalid"} ${sel}`}
              onClick={() => onPick(lap.id, "you")}
              title="Click to analyze this lap (A)"
            >
              <div className="lap-row-main">
                <span className="lapno">L{lap.lap_number}</span>
                <span className="laptime">{fmtTime(lap.lap_time)}</span>
                {lap.is_pb && <span className="badge pb">PB</span>}
                {lap.source === "imported" && <span className="badge imported">IMP</span>}
                {!lap.valid && <span className="badge cut">INV</span>}
                <span className="lap-actions" onClick={(e) => e.stopPropagation()}>
                  <button
                    className={`pick ${youId === lap.id ? "on-you" : ""}`}
                    title="Analyze this lap"
                    onClick={() => onPick(lap.id, "you")}
                  >
                    A
                  </button>
                  <button
                    className={`pick ${refId === lap.id ? "on-ref" : ""}`}
                    title="Use as reference lap"
                    onClick={() => onPick(lap.id, "ref")}
                  >
                    R
                  </button>
                  <button
                    className="pick danger"
                    title="Delete lap"
                    onClick={() => {
                      if (confirm(`Delete lap ${lap.lap_number} (${fmtTime(lap.lap_time)})?`)) onDelete(lap.id);
                    }}
                  >
                    ✕
                  </button>
                </span>
              </div>
              <div className="lap-row-sectors">
                {lap.s1 != null && lap.s2 != null && lap.s3 != null
                  ? `${lap.s1.toFixed(2)} · ${lap.s2.toFixed(2)} · ${lap.s3.toFixed(2)}`
                  : "no sector data"}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
