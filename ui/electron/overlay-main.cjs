// Lapsmith overlay shell: a transparent, frameless, always-on-top window
// over the game (game must be in borderless-windowed mode).
//
//   Ctrl+Alt+O  toggle click-through (drive without the overlay eating clicks)
//   Ctrl+Alt+H  hide/show
//
// Position and size persist between runs.

const { app, BrowserWindow, globalShortcut } = require("electron");
const fs = require("fs");
const path = require("path");

const statePath = path.join(app.getPath("userData"), "overlay-state.json");
let clickThrough = false;

function loadState() {
  try {
    return JSON.parse(fs.readFileSync(statePath, "utf-8"));
  } catch {
    return { x: 80, y: 80, width: 360, height: 190 };
  }
}

app.whenReady().then(() => {
  const state = loadState();
  const win = new BrowserWindow({
    ...state,
    transparent: true,
    frame: false,
    alwaysOnTop: true,
    resizable: true,
    skipTaskbar: true,
    hasShadow: false,
    minWidth: 220,
    minHeight: 120,
  });
  win.setAlwaysOnTop(true, "screen-saver"); // above borderless-windowed games
  // Electron's heuristic cache can pin an old overlay build — always start fresh.
  win.webContents.session.clearCache().then(() => {
    win.loadURL("http://localhost:8000/overlay.html");
  });
  globalShortcut.register("Control+Alt+R", () => win.webContents.reloadIgnoringCache());

  const saveBounds = () => {
    try {
      fs.writeFileSync(statePath, JSON.stringify(win.getBounds()));
    } catch {}
  };
  win.on("moved", saveBounds);
  win.on("resized", saveBounds);

  globalShortcut.register("Control+Alt+O", () => {
    clickThrough = !clickThrough;
    win.setIgnoreMouseEvents(clickThrough, { forward: true });
  });
  globalShortcut.register("Control+Alt+H", () => {
    win.isVisible() ? win.hide() : win.show();
  });
});

app.on("window-all-closed", () => app.quit());
