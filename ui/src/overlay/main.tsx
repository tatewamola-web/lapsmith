import React from "react";
import ReactDOM from "react-dom/client";
import CalloutWidget from "./CalloutWidget";
import DeltaWidget from "./DeltaWidget";
import Overlay from "./Overlay";
import "./overlay.css";

// one page, many widgets: ?w=<name> picks which one this window shows
const widget = new URLSearchParams(location.search).get("w") ?? "telemetry";
const View = widget === "delta" ? DeltaWidget : widget === "callouts" ? CalloutWidget : Overlay;

// Corner-resize scales the whole widget. Each widget zooms its OWN page
// against its design size, so widgets never affect each other's scale.
const BASE: Record<string, { w: number; h: number }> = {
  telemetry: { w: 290, h: 152 },
  delta: { w: 420, h: 64 },
  callouts: { w: 380, h: 54 },
};
function applyZoom() {
  const w = window.innerWidth;
  const h = window.innerHeight;
  let base = BASE[widget] ?? BASE.telemetry;
  if (widget === "telemetry" && w / h > 3) base = { w: 640, h: 110 }; // horizontal layout
  const zoom = Math.max(0.3, Math.min(3, Math.min(w / base.w, h / base.h)));
  (document.documentElement.style as CSSStyleDeclaration & { zoom: string }).zoom = String(zoom);
}
applyZoom();
window.addEventListener("resize", applyZoom);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <View />
  </React.StrictMode>
);
