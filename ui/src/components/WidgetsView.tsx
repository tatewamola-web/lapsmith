// Widgets tab: launch each in-game widget and change its settings. Settings
// are saved to the engine, and open widgets pick them up within ~3s.

import { useEffect, useState } from "react";

type RefMode = "fastest" | "pb";

interface Settings {
  delta: { range: number; ref: RefMode; showBar: boolean; showNumber: boolean };
  telemetry: { ref: RefMode };
}

const DEFAULTS: Settings = {
  delta: { range: 1.0, ref: "fastest", showBar: true, showNumber: true },
  telemetry: { ref: "fastest" },
};

async function launch(widget: string) {
  const r = await fetch(`/api/overlay/launch?widget=${widget}`, { method: "POST" });
  const d = await r.json().catch(() => ({ ok: false }));
  if (!d.ok) alert(`Could not launch: ${d.error ?? "unknown error"}`);
}

function RefPicker({ value, onChange }: { value: RefMode; onChange: (v: RefMode) => void }) {
  return (
    <label className="wset">
      <span>Compare against</span>
      <select value={value} onChange={(e) => onChange(e.target.value as RefMode)}>
        <option value="fastest">Fastest lap (incl. rivals)</option>
        <option value="pb">My personal best</option>
      </select>
    </label>
  );
}

export default function WidgetsView() {
  const [s, setS] = useState<Settings>(DEFAULTS);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    fetch("/api/widgets/settings")
      .then((r) => r.json())
      .then((d) => setS({
        delta: { ...DEFAULTS.delta, ...d.delta },
        telemetry: { ...DEFAULTS.telemetry, ...d.telemetry },
      }))
      .catch(() => {});
  }, []);

  const update = (next: Settings) => {
    setS(next);
    fetch("/api/widgets/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(next),
    }).then(() => {
      setSaved(true);
      setTimeout(() => setSaved(false), 1200);
    });
  };

  return (
    <div className="sessions-wrap">
      <p className="widgets-intro">
        Widgets float over the game — set LMU to <b>borderless windowed</b>. Drag to move,
        resize from a corner to scale. <b>Ctrl+Alt+O</b> click-through ·{" "}
        <b>Ctrl+Alt+H</b> hide all · <b>Ctrl+Alt+R</b> reload.
        {saved && <span className="widgets-saved"> ✓ saved</span>}
      </p>

      <div className="widget-card">
        <div className="widget-head">
          <div>
            <b>Delta Bar</b>
            <span>Live gap to your reference lap, iRacing-style. Green fill = ahead, red = behind; the number turns green while you're gaining right now.</span>
          </div>
          <button className="pick widget-launch" onClick={() => launch("delta")}>▶ LAUNCH</button>
        </div>
        <div className="widget-settings">
          <RefPicker value={s.delta.ref} onChange={(ref) => update({ ...s, delta: { ...s.delta, ref } })} />
          <label className="wset">
            <span>Bar range ±{s.delta.range.toFixed(1)}s</span>
            <input
              type="range" min={0.2} max={3} step={0.1} value={s.delta.range}
              onChange={(e) => update({ ...s, delta: { ...s.delta, range: Number(e.target.value) } })}
            />
          </label>
          <label className="wset check">
            <input type="checkbox" checked={s.delta.showBar}
              onChange={(e) => update({ ...s, delta: { ...s.delta, showBar: e.target.checked } })} />
            Show bar
          </label>
          <label className="wset check">
            <input type="checkbox" checked={s.delta.showNumber}
              onChange={(e) => update({ ...s, delta: { ...s.delta, showNumber: e.target.checked } })} />
            Show number
          </label>
        </div>
      </div>

      <div className="widget-card">
        <div className="widget-head">
          <div>
            <b>Input Trace</b>
            <span>Rolling throttle/brake trace against your reference lap, pedal bars, gear with rev ring, lap times. Per-panel toggles and horizontal layout live in its ⚙ menu.</span>
          </div>
          <button className="pick widget-launch" onClick={() => launch("telemetry")}>▶ LAUNCH</button>
        </div>
        <div className="widget-settings">
          <RefPicker value={s.telemetry.ref} onChange={(ref) => update({ ...s, telemetry: { ref } })} />
        </div>
      </div>
    </div>
  );
}
