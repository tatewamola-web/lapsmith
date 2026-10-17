import React from "react";
import ReactDOM from "react-dom/client";
import DeltaWidget from "./DeltaWidget";
import Overlay from "./Overlay";
import "./overlay.css";

// one page, many widgets: ?w=<name> picks which one this window shows
const widget = new URLSearchParams(location.search).get("w") ?? "telemetry";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>{widget === "delta" ? <DeltaWidget /> : <Overlay />}</React.StrictMode>
);
