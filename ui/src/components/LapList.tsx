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
      <div className="laplist-scroll">
        <table className="laplist">
          <thead>
            <tr>
              <th>#</th>
              <th>Time</th>
              <th>S1</th>
              <th>S2</th>
              <th>S3</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {shown.map((lap) => (
              <tr key={lap.id} className={lap.valid ? "" : "invalid"}>
                <td>
                  {lap.lap_number}
                  {lap.is_pb && <span className="badge pb">PB</span>}
                  {lap.source === "imported" && <span className="badge imported">IMP</span>}
                  {!lap.valid && <span className="badge cut">INV</span>}
                </td>
                <td className="time">{fmtTime(lap.lap_time)}</td>
                <td>{lap.s1 != null ? lap.s1.toFixed(2) : "–"}</td>
                <td>{lap.s2 != null ? lap.s2.toFixed(2) : "–"}</td>
                <td>{lap.s3 != null ? lap.s3.toFixed(2) : "–"}</td>
                <td>
                  <button
                    className={`pick ${youId === lap.id ? "on-you" : ""}`}
                    title="Analyze this lap"
                    onClick={() => onPick(lap.id, "you")}
                  >
                    A
                  </button>{" "}
                  <button
                    className={`pick ${refId === lap.id ? "on-ref" : ""}`}
                    title="Use as reference lap"
                    onClick={() => onPick(lap.id, "ref")}
                  >
                    R
                  </button>{" "}
                  <button
                    className="pick danger"
                    title="Delete lap"
                    onClick={() => {
                      if (confirm(`Delete lap ${lap.lap_number} (${fmtTime(lap.lap_time)})?`)) onDelete(lap.id);
                    }}
                  >
                    ✕
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
