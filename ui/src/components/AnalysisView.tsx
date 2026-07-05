// Analysis: lap library sidebar + comparison charts.

import type { ComparePayload, LapMeta } from "../api";
import { fmtTime } from "../api";
import LapList from "./LapList";
import TrackMap from "./TrackMap";
import { DeltaChart, PedalChart, SpeedChart, SteeringChart } from "./Charts";

interface Props {
  laps: LapMeta[];
  youId: number | null;
  refId: number | null;
  cmp: ComparePayload | null;
  sessionFilter: number | null;
  onPick: (id: number, slot: "you" | "ref") => void;
  onDelete: (id: number) => void;
  onClearFilter: () => void;
}

export default function AnalysisView({
  laps, youId, refId, cmp, sessionFilter, onPick, onDelete, onClearFilter,
}: Props) {
  const finalDelta = cmp ? cmp.delta[cmp.delta.length - 1] : null;

  return (
    <div className="analysis-grid">
      <aside className="sidebar">
        <LapList
          laps={laps}
          youId={youId}
          refId={refId}
          sessionFilter={sessionFilter}
          onPick={onPick}
          onDelete={onDelete}
          onClearFilter={onClearFilter}
        />
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
              ? "No laps here yet. Drive — laps appear as you complete them."
              : "Pick a lap to analyze (A) and a reference lap (R) from the list."}
          </div>
        )}
      </main>
    </div>
  );
}
