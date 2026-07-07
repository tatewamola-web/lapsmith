import { useState } from "react";
import type { LapMeta } from "../api";
import { fmtTime } from "../api";

interface Props {
  laps: LapMeta[];
  youId: number | null;
  refId: number | null;
  sessionFilter: number | null;
  combo: string;                       // "track|car" or "all"
  combos: { key: string; label: string }[];
  onCombo: (key: string) => void;
  onPick: (id: number, slot: "you" | "ref") => void;
  onDelete: (id: number) => void;
  onClearFilter: () => void;
}

export default function LapList({
  laps, youId, refId, sessionFilter, combo, combos, onCombo,
  onPick, onDelete, onClearFilter,
}: Props) {
  const [validOnly, setValidOnly] = useState(false);
  const shown = validOnly ? laps.filter((l) => l.valid) : laps;

  // Purple = fastest sector among the laps in view (motorsport convention).
  const best = { s1: Infinity, s2: Infinity, s3: Infinity };
  for (const l of shown) {
    if (!l.valid) continue;
    if (l.s1 != null && l.s1 < best.s1) best.s1 = l.s1;
    if (l.s2 != null && l.s2 < best.s2) best.s2 = l.s2;
    if (l.s3 != null && l.s3 < best.s3) best.s3 = l.s3;
  }
  const sectorCls = (valid: boolean, v: number | null, b: number) =>
    valid && v != null && Math.abs(v - b) < 0.005 ? "sec purple" : "sec";

  return (
    <div>
      <div className="laplist-head" style={{ flexWrap: "wrap" }}>
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
        {sessionFilter == null && (
          <select className="combo-select" value={combo} onChange={(e) => onCombo(e.target.value)}>
            {combos.map((c) => (
              <option key={c.key} value={c.key}>{c.label}</option>
            ))}
            <option value="all">All laps · every track</option>
          </select>
        )}
      </div>
      <div className="lap-rows">
        {shown.map((lap) => {
          const sel = youId === lap.id ? "sel-you" : refId === lap.id ? "sel-ref" : "";
          const analyzable = lap.has_data !== false;
          return (
            <div
              key={lap.id}
              className={`lap-row ${lap.valid ? "" : "invalid"} ${sel}`}
              onClick={() => analyzable && onPick(lap.id, "you")}
              title={analyzable ? "Click to analyze this lap (A)" : "Game-history lap: time only, no telemetry to analyze"}
            >
              <div className="lap-row-main">
                <span className="lapno">L{lap.lap_number}</span>
                <span className="laptime">{fmtTime(lap.lap_time)}</span>
                {lap.is_pb && <span className="badge pb">PB</span>}
                {lap.source === "imported" && <span className="badge imported">IMP</span>}
                {lap.source === "game-log" && <span className="badge log">LOG</span>}
                {lap.source === "opponent" && (
                  <span className="badge rival" title={`Captured live from ${lap.driver}`}>
                    {lap.driver.split(" ")[0].toUpperCase()}
                  </span>
                )}
                {!lap.valid && <span className="badge cut">INV</span>}
                <span className="lap-actions" onClick={(e) => e.stopPropagation()}>
                  {analyzable && (
                    <>
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
                    </>
                  )}
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
                {lap.s1 != null && lap.s2 != null && lap.s3 != null ? (
                  <>
                    <span className={sectorCls(!!lap.valid, lap.s1, best.s1)}>{lap.s1.toFixed(2)}</span>
                    {" · "}
                    <span className={sectorCls(!!lap.valid, lap.s2, best.s2)}>{lap.s2.toFixed(2)}</span>
                    {" · "}
                    <span className={sectorCls(!!lap.valid, lap.s3, best.s3)}>{lap.s3.toFixed(2)}</span>
                  </>
                ) : (
                  "no sector data"
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
