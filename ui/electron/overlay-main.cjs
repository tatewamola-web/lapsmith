// Lapsmith widget host: one Electron process, one transparent always-on-top
// window per widget (game must be in borderless-windowed mode).
//
//   electron overlay-main.cjs --widget=telemetry     (default)
//   electron overlay-main.cjs --widget=delta
//
// Launching again with a widget name opens that widget in the running host
// (or reloads it if it's already open). Each widget remembers its own
// position and size.
//
//   Ctrl+Alt+O  toggle click-through on all widgets
//   Ctrl+Alt+H  hide/show all widgets
//   Ctrl+Alt+R  reload all widgets

const { app, BrowserWindow, globalShortcut } = require("electron");
const fs = require("fs");
const path = require("path");

// baseline layout size per widget; corner-resizing zooms relative to this
const WIDGETS = {
  telemetry: { width: 290, height: 152, minWidth: 170, minHeight: 52 },
  delta: { width: 420, height: 64, minWidth: 140, minHeight: 28 },
  callouts: { width: 380, height: 54, minWidth: 140, minHeight: 26 },
};

const windows = {};
let clickThrough = false;

function widgetFromArgv(argv) {
  const arg = argv.find((a) => a.startsWith("--widget="));
  const name = arg ? arg.split("=")[1] : "telemetry";
  return WIDGETS[name] ? name : "telemetry";
}

const statePath = (name) => path.join(app.getPath("userData"), `widget-${name}.json`);

function loadBounds(name) {
  try {
    return JSON.parse(fs.readFileSync(statePath(name), "utf-8"));
  } catch {
    const b = WIDGETS[name];
    const y = { delta: 30, callouts: 100, telemetry: 160 }[name] ?? 160;
    return { x: 80, y, width: b.width, height: b.height };
  }
}

function openWidget(name) {
  if (windows[name] && !windows[name].isDestroyed()) {
    windows[name].show();
    windows[name].webContents.reloadIgnoringCache();
    return;
  }
  const cfg = WIDGETS[name];
  const win = new BrowserWindow({
    ...loadBounds(name),
    transparent: true,
    frame: false,
    alwaysOnTop: true,
    resizable: true,
    skipTaskbar: true,
    hasShadow: false,
    minWidth: cfg.minWidth,
    minHeight: cfg.minHeight,
    // Chromium slows timers/rendering in windows without focus — and while
    // you drive, the game always has focus. Overlays must opt out.
    webPreferences: { backgroundThrottling: false },
  });
  windows[name] = win;
  win.setAlwaysOnTop(true, "screen-saver");
  win.setIgnoreMouseEvents(clickThrough, { forward: true });
  win.webContents.session.clearCache().then(() => {
    win.loadURL(`http://127.0.0.1:8000/overlay.html?w=${name}`);
  });

  // Scaling happens inside each widget's page (CSS zoom). Electron's
  // setZoomFactor is shared by every window on the same origin — all
  // widgets are localhost:8000 — so one widget's zoom leaked into the rest.
  const saveBounds = () => {
    try {
      fs.writeFileSync(statePath(name), JSON.stringify(win.getBounds()));
    } catch {}
  };
  win.on("moved", saveBounds);
  win.on("resized", saveBounds);
  win.on("closed", () => delete windows[name]);
}

if (!app.requestSingleInstanceLock()) {
  app.quit();
}
app.on("second-instance", (_e, argv) => openWidget(widgetFromArgv(argv)));

app.whenReady().then(() => {
  openWidget(widgetFromArgv(process.argv));

  const all = () => Object.values(windows).filter((w) => !w.isDestroyed());
  globalShortcut.register("Control+Alt+O", () => {
    clickThrough = !clickThrough;
    all().forEach((w) => w.setIgnoreMouseEvents(clickThrough, { forward: true }));
  });
  globalShortcut.register("Control+Alt+H", () => {
    const anyVisible = all().some((w) => w.isVisible());
    all().forEach((w) => (anyVisible ? w.hide() : w.show()));
  });
  globalShortcut.register("Control+Alt+R", () =>
    all().forEach((w) => w.webContents.reloadIgnoringCache())
  );
});

app.on("window-all-closed", () => app.quit());
