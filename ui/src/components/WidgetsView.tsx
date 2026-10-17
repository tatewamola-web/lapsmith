// Widget hub: switch each in-game widget on/off and change its settings.
// Everything is saved to the engine; open widgets pick changes up within
// ~3s and close themselves when switched off.

import { useEffect, useState } from "react";

type RefMode = "fastest" | "pb";

interface Settings {
  general: { autohide: boolean };
  voice: { enabled: boolean; callouts: boolean; spotter: boolean };
  delta: { enabled: boolean; range: number; ref: RefMode; showBar: boolean; showNumber: boolean };
  telemetry: {
    enabled: boolean; ref: RefMode;
    trace: boolean; inputs: boolean; gear: boolean; times: boolean;
    horizontal: boolean; autohide: boolean;
  };
  callouts: { enabled: boolean; lead: number };
}
type Name = "delta" | "telemetry" | "callouts";

const DEFAULTS: Settings = {
  general: { autohide: true },
  voice: { enabled: false, callouts: true, spotter: false },
  delta: { enabled: false, range: 1.0, ref: "fastest", showBar: true, showNumber: true },
  telemetry: {
    enabled: false, ref: "fastest",
    trace: true, inputs: true, gear: true, times: true, horizontal: false, autohide: true,
  },
  callouts: { enabled: false, lead: 250 },
};

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

function Check({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="wset check">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      {label}
    </label>
  );
}

// Defined outside WidgetsView so React keeps the same component identity
// across renders — otherwise sliders remount and drop out of a drag.
function Card({ enabled, onToggle, title, desc, children }: {
  enabled: boolean; onToggle: () => void; title: string; desc: string; children: React.ReactNode;
}) {
  return (
    <div className={`widget-card ${enabled ? "on" : ""}`}>
      <div className="widget-head">
        <div>
          <b>{title}</b>
          <span>{desc}</span>
        </div>
        <button
          className={`widget-switch ${enabled ? "on" : ""}`}
          onClick={onToggle}
          title={enabled ? "Turn off (closes the widget)" : "Turn on (opens the widget)"}
        >
          <span className="knob" />
        </button>
      </div>
      <div className="widget-settings">{children}</div>
    </div>
  );
}

export default function WidgetsView() {
  const [s, setS] = useState<Settings>(DEFAULTS);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    const load = () =>
      fetch("/api/widgets/settings")
        .then((r) => r.json())
        .then((d) =>
          setS({
            general: { ...DEFAULTS.general, ...d.general },
            voice: { ...DEFAULTS.voice, ...d.voice },
            delta: { ...DEFAULTS.delta, ...d.delta },
            telemetry: { ...DEFAULTS.telemetry, ...d.telemetry },
            callouts: { ...DEFAULTS.callouts, ...d.callouts },
          })
        )
        .catch(() => {});
    load();
  }, []);

  const save = async (next: Settings) => {
    setS(next);
    await fetch("/api/widgets/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(next),
    });
    setSaved(true);
    setTimeout(() => setSaved(false), 1200);
  };

  const set = <N extends keyof Settings>(name: N, patch: Partial<Settings[N]>) =>
    save({ ...s, [name]: { ...s[name], ...patch } });

  const toggleWidget = async (name: Name, on: boolean) => {
    await set(name, { enabled: on } as Partial<Settings[Name]>);
    if (on) {
      const r = await fetch(`/api/overlay/launch?widget=${name}`, { method: "POST" });
      const d = await r.json().catch(() => ({ ok: false }));
      if (!d.ok) alert(`Could not launch: ${d.error ?? "unknown error"}`);
    }
  };

  return (
    <div className="sessions-wrap">
      <p className="widgets-intro">
        Widgets float over the game — set LMU to <b>borderless windowed</b>. Drag to move,
        resize from a corner to scale. <b>Ctrl+Alt+O</b> click-through ·{" "}
        <b>Ctrl+Alt+H</b> hide all · <b>Ctrl+Alt+R</b> reload.
        {saved && <span className="widgets-saved"> ✓ saved</span>}
      </p>

      <label className="widgets-general">
        <input type="checkbox" checked={s.general.autohide}
          onChange={(e) => set("general", { autohide: e.target.checked })} />
        <span><b>Hide in menus</b> — every widget disappears in the garage and menus and comes back on track</span>
      </label>

      <Card
        enabled={s.voice.enabled}
        onToggle={() => set("voice", { enabled: !s.voice.enabled })}
        title="Voice"
        desc="A race-engineer voice through your speakers or headset. Runs locally with a neural voice, no internet. Works whether or not any widget is open."
      >
        <Check label="Speak corner callouts" checked={s.voice.callouts} onChange={(v) => set("voice", { callouts: v })} />
        <Check label="Spotter (beta) — car left / right / clear" checked={s.voice.spotter} onChange={(v) => set("voice", { spotter: v })} />
        <button className="pick" onClick={async () => {
          const d = await (await fetch("/api/voice/test", { method: "POST" })).json().catch(() => ({ ok: false }));
          if (!d.ok) alert(d.error ?? "Voice test failed");
        }}>▶ TEST VOICE</button>
      </Card>

      <Card
        enabled={s.callouts.enabled}
        onToggle={() => toggleWidget("callouts", !s.callouts.enabled)}
        title="Corner Callouts (on screen)"
        desc="One short instruction per corner as you approach it — e.g. “T1 · Brake slightly later, throttle sooner”. Learned from your laps and the fastest driving recorded at each track."
      >
        <label className="wset">
          <span>Show {s.callouts.lead}m before the corner</span>
          <input
            type="range" min={100} max={500} step={25} value={s.callouts.lead}
            onChange={(e) => set("callouts", { lead: Number(e.target.value) })}
          />
        </label>
      </Card>

      <Card
        enabled={s.delta.enabled}
        onToggle={() => toggleWidget("delta", !s.delta.enabled)}
        title="Delta Bar"
        desc="Live gap to your reference lap, iRacing-style. Green fill = ahead, red = behind; the number turns green while you're gaining right now."
      >
        <RefPicker value={s.delta.ref} onChange={(ref) => set("delta", { ref })} />
        <label className="wset">
          <span>Bar range ±{s.delta.range.toFixed(1)}s</span>
          <input
            type="range" min={0.2} max={3} step={0.1} value={s.delta.range}
            onChange={(e) => set("delta", { range: Number(e.target.value) })}
          />
        </label>
        <Check label="Bar" checked={s.delta.showBar} onChange={(v) => set("delta", { showBar: v })} />
        <Check label="Number" checked={s.delta.showNumber} onChange={(v) => set("delta", { showNumber: v })} />
      </Card>

      <Card
        enabled={s.telemetry.enabled}
        onToggle={() => toggleWidget("telemetry", !s.telemetry.enabled)}
        title="Input Trace"
        desc="Rolling throttle/brake trace against your reference lap (ABS glows amber), pedal bars, gear with rev ring, lap times."
      >
        <RefPicker value={s.telemetry.ref} onChange={(ref) => set("telemetry", { ref })} />
        <Check label="Trace" checked={s.telemetry.trace} onChange={(v) => set("telemetry", { trace: v })} />
        <Check label="Pedals" checked={s.telemetry.inputs} onChange={(v) => set("telemetry", { inputs: v })} />
        <Check label="Gear + revs" checked={s.telemetry.gear} onChange={(v) => set("telemetry", { gear: v })} />
        <Check label="Lap times" checked={s.telemetry.times} onChange={(v) => set("telemetry", { times: v })} />
        <Check label="Horizontal layout" checked={s.telemetry.horizontal} onChange={(v) => set("telemetry", { horizontal: v })} />
      </Card>
    </div>
  );
}
