// Data-driven coach: regression across all your laps on this combo finds
// which habit at which corner costs YOU the most time — ranked by the
// expected gain of driving the corner like your own fastest laps.

import { useEffect, useState } from "react";
import type { LapMeta } from "../api";

interface Tip {
  corner: string;
  apex_pct: number;
  message: string;
  gain: number;
  laps_used: number;
}

interface CoachResult {
  laps_analyzed: number;
  rivals_analyzed?: number;
  model?: string;
  tips: Tip[];
  opportunities?: Tip[];
  note?: string;
}

export default function CoachPanel({ meta }: { meta: LapMeta }) {
  const [result, setResult] = useState<CoachResult | null>(null);

  useEffect(() => {
    let stale = false;
    const q = new URLSearchParams({
      track: meta.track,
      car_class: meta.car_class || "",
      car: meta.car,
    });
    fetch(`/api/coach?${q}`)
      .then((r) => r.json())
      .then((d) => !stale && setResult(d))
      .catch(() => !stale && setResult(null));
    return () => {
      stale = true;
    };
  }, [meta.track, meta.car_class, meta.car]);

  if (!result) return null;

  return (
    <div className="panel">
      <h3>
        Coach · {result.laps_analyzed} of your laps
        {result.rivals_analyzed ? ` · ${result.rivals_analyzed} rival laps` : ""}
      </h3>
      {(result.opportunities?.length ?? 0) > 0 && (
        <>
          <div className="coach-section">Biggest opportunities — vs the fastest driving seen here</div>
          <ol className="coach-list">
            {result.opportunities!.map((t, i) => (
              <li key={`o${i}`}>
                <b>{t.corner}</b> <span className="dim">@{t.apex_pct.toFixed(0)}%</span>{" "}
                — {t.message}
                <span className="coach-gain">≈ {t.gain.toFixed(2)}s</span>
              </li>
            ))}
          </ol>
          <div className="coach-section">Habit fixes — from your own lap-to-lap variation</div>
        </>
      )}
      {result.tips.length === 0 ? (
        <div className="hint">
          {result.note ??
            "No statistically clear habits found yet — more laps sharpen the model."}
        </div>
      ) : (
        <ol className="coach-list">
          {result.tips.map((t, i) => (
            <li key={i}>
              <b>{t.corner}</b> <span className="dim">@{t.apex_pct.toFixed(0)}%</span>{" "}
              — {t.message}
              <span className="coach-gain">≈ {t.gain.toFixed(2)}s</span>
              <span className="dim"> · {t.laps_used} laps</span>
            </li>
          ))}
        </ol>
      )}
      <div className="hint">
        {result.model ?? "regression"} · corner time vs braking point, min
        speed, throttle point across your own laps — gains estimate moving
        your median habit to your demonstrated best
      </div>
    </div>
  );
}
