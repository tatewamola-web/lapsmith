// Analysis: lap library sidebar + comparison charts.

import { useEffect, useState } from "react";
import type { ComparePayload, IdealLap, Insights, LapMeta } from "../api";
import { fmtTime, getIdeal, getLapData } from "../api";
import LapList from "./LapList";
import RacingLine from "./RacingLine";
import TrackMap from "./TrackMap";
import { ChartMarkers, DeltaChart, PedalChart, SpeedChart, SteeringChart } from "./Charts";

/** "T4-5 Variante della Roggia" -> "T4-5". Unnamed corners get C-numbers
 * so they can't be mistaken for official turn numbers. */
export function officialLabel(name: string, n: number): string {
  return name ? name.split(" ")[0] : `C${n}`;
}

interface Props {
  laps: LapMeta[];
  youId: number | null;
  refId: number | null;
  cmp: ComparePayload | null;
  insights: Insights | null;
  sessionFilter: number | null;
  combo: string;
  combos: { key: string; label: string }[];
  onCombo: (key: string) => void;
  onPick: (id: number, slot: "you" | "ref") => void;
  onDelete: (id: number) => void;
  onClearFilter: () => void;
}

function IdealPanel({ ideal }: { ideal: IdealLap }) {
  return (
    <div className="panel">
      <h3>Theoretical Ideal Lap · best sectors combined</h3>
      <div style={{ fontFamily: "var(--mono)", fontSize: 13, lineHeight: 2 }}>
        <div style={{ display: "flex", justifyContent: "space-between" }}>
          <span style={{ color: "var(--text-dim)" }}>
            {ideal.s1.toFixed(3)} · {ideal.s2.toFixed(3)} · {ideal.s3.toFixed(3)}
          </span>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between" }}>
          <span style={{ color: "var(--text-faint)" }}>ideal</span>
          <b style={{ color: "var(--pb)", fontSize: 17 }}>{fmtTime(ideal.total)}</b>
        </div>
        {ideal.pb_time != null && (
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span style={{ color: "var(--text-faint)" }}>real PB</span>
            <span>{fmtTime(ideal.pb_time)}</span>
          </div>
        )}
        {ideal.gap_to_pb != null && ideal.gap_to_pb > 0.001 && (
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span style={{ color: "var(--text-faint)" }}>in your hands</span>
            <span style={{ color: "var(--gain)" }}>-{ideal.gap_to_pb.toFixed(3)}s</span>
          </div>
        )}
      </div>
      <div className="hint">from {ideal.laps_considered} laps with sector data (incl. game history)</div>
    </div>
  );
}

function CornerPanel({ ins }: { ins: Insights }) {
  return (
    <div className="panel">
      <h3>
        Corner Analysis · {ins.corners.length} corners detected ·{" "}
        {ins.corner_loss_total > 0 ? `${ins.corner_loss_total.toFixed(2)}s recoverable` : "no losses found"}
      </h3>
      <table className="corner-table">
        <thead>
          <tr>
            <th>Corner</th>
            <th>At</th>
            <th>Sector</th>
            <th>Loss</th>
            <th>Apex (you/ref)</th>
            <th>What's happening</th>
          </tr>
        </thead>
        <tbody>
          {ins.corners.map((c) => (
            <tr key={c.n} className={ins.worst.includes(c.n) ? "worst" : ""}>
              <td className="num">{c.name || `T${c.n}`}</td>
              <td className="num">{c.apex_pct.toFixed(0)}%</td>
              <td className="num">{c.sector > 0 ? `S${c.sector}` : "–"}</td>
              <td className={`num ${c.loss > 0.03 ? "loss-pos" : c.loss < -0.03 ? "loss-neg" : ""}`}>
                {c.loss >= 0 ? "+" : ""}
                {c.loss.toFixed(3)}
              </td>
              <td className="num">
                {c.apex_kmh_you.toFixed(0)} / {c.apex_kmh_ref.toFixed(0)} km/h
              </td>
              <td className="advice">{c.advice}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="hint">worst corners highlighted · corners detected from track geometry · loss is time vs reference across that corner</div>
    </div>
  );
}

export default function AnalysisView({
  laps, youId, refId, cmp, insights, sessionFilter, combo, combos, onCombo,
  onPick, onDelete, onClearFilter,
}: Props) {
  const finalDelta = cmp ? cmp.delta[cmp.delta.length - 1] : null;
  const [ideal, setIdeal] = useState<IdealLap | null>(null);
  const [soloCmp, setSoloCmp] = useState<ComparePayload | null>(null);

  // Solo mode: one lap picked, no reference — build a playback-only
  // payload from the lap's own channels so it can still be watched.
  const soloLap = refId == null || refId === youId
    ? laps.find((l) => l.id === youId && l.has_data !== false) ?? null
    : null;
  useEffect(() => {
    if (!soloLap || cmp) {
      setSoloCmp(null);
      return;
    }
    let stale = false;
    getLapData(soloLap.id)
      .then((d) => {
        if (stale) return;
        const ch = {
          speed: d.speed,
          throttle: d.throttle,
          brake: d.brake,
          steering: d.steering,
          gear: d.gear.map((g) => Math.round(g)),
          lap_time: d.lap_time,
        };
        const edge = (d as unknown as { track_edge?: number[] }).track_edge;
        setSoloCmp({
          dist: d.lap_dist,
          delta: d.lap_dist.map(() => 0),
          lap: ch,
          ref: ch,
          map: {
            x: d.pos_x,
            z: d.pos_z,
            you_x: d.pos_x,
            you_z: d.pos_z,
            width: edge ? edge.map((e) => Math.min(Math.max(Math.abs(e) * 2, 6), 30)) : undefined,
          },
          lap_meta: soloLap,
          ref_meta: soloLap,
        });
      })
      .catch(() => !stale && setSoloCmp(null));
    return () => {
      stale = true;
    };
  }, [soloLap?.id, cmp]);

  useEffect(() => {
    const m = cmp?.lap_meta;
    if (!m) {
      setIdeal(null);
      return;
    }
    let stale = false;
    getIdeal(m.game, m.track, m.car)
      .then((i) => !stale && setIdeal(i))
      .catch(() => !stale && setIdeal(null));
    return () => {
      stale = true;
    };
  }, [cmp?.lap_meta?.game, cmp?.lap_meta?.track, cmp?.lap_meta?.car]);

  // Sector lines + corner ticks for the delta/speed charts, in % of lap.
  const maxDist = cmp ? cmp.dist[cmp.dist.length - 1] : 0;
  const markers: ChartMarkers | undefined =
    cmp && insights
      ? {
          sectors: [
            { pct: (insights.s1_dist / maxDist) * 100, label: "S1|S2" },
            { pct: (insights.s2_dist / maxDist) * 100, label: "S2|S3" },
          ].filter((s) => s.pct > 0),
          corners: insights.corners.map((c) => ({ pct: c.apex_pct, label: officialLabel(c.name, c.n) })),
        }
      : undefined;

  return (
    <div className="analysis-grid">
      <aside className="sidebar">
        <LapList
          laps={laps}
          youId={youId}
          refId={refId}
          sessionFilter={sessionFilter}
          combo={combo}
          combos={combos}
          onCombo={onCombo}
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
                  <DeltaChart cmp={cmp} markers={markers} />
                </div>
                <div className="panel">
                  <h3>Speed</h3>
                  <SpeedChart cmp={cmp} markers={markers} />
                </div>
                <div className="panel">
                  <h3>Throttle / Brake</h3>
                  <PedalChart cmp={cmp} markers={markers} />
                </div>
                <div className="panel">
                  <h3>Steering</h3>
                  <SteeringChart cmp={cmp} markers={markers} />
                </div>
                {insights && insights.corners.length > 0 && <CornerPanel ins={insights} />}
              </div>
              <div>
                <div className="panel">
                  <h3>Track · time gain/loss</h3>
                  <TrackMap cmp={cmp} insights={insights} />
                </div>
                <div className="panel">
                  <h3>Racing Line · A vs R</h3>
                  <RacingLine cmp={cmp} insights={insights} />
                </div>
                {ideal && <IdealPanel ideal={ideal} />}
                <div className="panel">
                  <h3>Legend</h3>
                  <div style={{ fontSize: 12.5, color: "var(--text-dim)", lineHeight: 1.9 }}>
                    <div><span style={{ color: "var(--you)" }}>━</span> solid = your lap (A)</div>
                    <div><span style={{ color: "var(--ref)" }}>┅</span> dashed = reference lap (R)</div>
                    <div><span style={{ color: "var(--loss)" }}>━</span> losing time / brake</div>
                    <div><span style={{ color: "var(--gain)" }}>━</span> gaining time / throttle</div>
                    <div><span style={{ color: "var(--pb)" }}>●</span> corner markers (T-numbers)</div>
                  </div>
                  <div className="hint">charts: scroll to zoom · drag to box-zoom · double-click resets</div>
                </div>
              </div>
            </div>
          </>
        ) : soloCmp ? (
          <>
            <div className="compare-head">
              <span className="you">
                LAP {soloCmp.lap_meta.lap_number} · {fmtTime(soloCmp.lap_meta.lap_time)}
              </span>
              <span className="vs">solo — pick a reference (R) to compare</span>
            </div>
            <div className="grid-2col">
              <div>
                <div className="panel">
                  <h3>Lap Playback</h3>
                  <RacingLine cmp={soloCmp} insights={null} solo />
                </div>
              </div>
            </div>
          </>
        ) : (
          <div className="placeholder">
            {laps.length === 0
              ? "No laps here yet. Drive — laps appear as you complete them."
              : laps.every((l) => l.has_data === false)
                ? "This session was imported from the game's logs: lap and sector times only (shown on the left). Trace analysis, racing lines, and playback need laps recorded live with the engine running."
                : "Pick a lap to analyze (A) and a reference lap (R) from the list."}
          </div>
        )}
      </main>
    </div>
  );
}
