const { app, BrowserWindow, globalShortcut, ipcMain, dialog, screen } = require("electron");
const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");
const WebSocket = require("ws");
const { nextDelayMs } = require("./reconnect");

const ROOT = path.join(__dirname, "..");
const WS_URL = "ws://127.0.0.1:8765";

let overlay = null;
let sidecar = null;
let ws = null;
let reconnectTimer = null;
let attempt = 0;
let quitting = false;
let lastStatus = null;
let lastContext = null;
let lastHistory = null;
const aux = {};

function userDataDir() {
  try {
    return app.getPath("userData");
  } catch {
    return path.join(ROOT, "data");
  }
}

function loadFullConfig() {
  const defaultsPath = path.join(ROOT, "backend", "config", "defaults.json");
  let data = {
    llm: {},
    stt: {},
    question_detection: {},
    audio: {},
    overlay: {
      always_on_top: true,
      content_protection: true,
      opacity: 0.92,
      hotkey_toggle_visibility: "CommandOrControl+Shift+H",
      hotkey_panic_hide: "CommandOrControl+Shift+Escape",
    },
    storage: { session_history_enabled: true },
  };
  try {
    data = { ...data, ...JSON.parse(fs.readFileSync(defaultsPath, "utf8")) };
  } catch (err) {
    console.error("failed to read defaults.json", err.message);
  }
  const userPath = path.join(userDataDir(), "config.json");
  if (fs.existsSync(userPath)) {
    try {
      const user = JSON.parse(fs.readFileSync(userPath, "utf8"));
      for (const key of Object.keys(user || {})) {
        if (user[key] && typeof user[key] === "object" && !Array.isArray(user[key])) {
          data[key] = { ...(data[key] || {}), ...user[key] };
        } else {
          data[key] = user[key];
        }
      }
    } catch (err) {
      console.error("failed to read user config.json", err.message);
    }
  }
  return data;
}

function loadOverlayConfig() {
  return loadFullConfig().overlay;
}

function pythonPath() {
  const win = path.join(ROOT, ".venv", "Scripts", "python.exe");
  const nix = path.join(ROOT, ".venv", "bin", "python");
  if (fs.existsSync(win)) return win;
  if (fs.existsSync(nix)) return nix;
  return process.platform === "win32" ? "python" : "python3";
}

function rendererWindows() {
  const wins = [];
  if (overlay && !overlay.isDestroyed()) wins.push(overlay);
  for (const name of ["Setup", "History", "Settings"]) {
    if (aux[name] && !aux[name].isDestroyed()) wins.push(aux[name]);
  }
  return wins;
}

function sendToRenderers(channel, data) {
  for (const win of rendererWindows()) {
    win.webContents.send(channel, data);
  }
}

function sendBackendState(data) {
  sendToRenderers("backend-state", data);
}

function connectWs() {
  if (quitting) return;
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
    return;
  }
  ws = new WebSocket(WS_URL);
  ws.on("open", () => {
    attempt = 0;
    console.log("ws connected", WS_URL);
    sendBackendState({ connected: true });
  });
  ws.on("message", (data) => {
    let obj;
    try {
      obj = JSON.parse(data.toString());
    } catch {
      return;
    }
    if (obj && obj.type === "status") lastStatus = obj;
    if (obj && obj.type === "context_updated") lastContext = obj;
    if (obj && obj.type === "history_data") lastHistory = obj;
    sendToRenderers("ws-event", obj);
  });
  ws.on("close", () => {
    ws = null;
    sendBackendState({ connected: false });
    scheduleReconnect();
  });
  ws.on("error", (err) => {
    console.error("ws error", err.message);
  });
}

function scheduleReconnect() {
  if (quitting || reconnectTimer) return;
  const delay = nextDelayMs(attempt);
  attempt += 1;
  console.log(`ws reconnect in ${delay}ms`);
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connectWs();
  }, delay);
}

function sidecarLaunch() {
  if (app.isPackaged) {
    const name = process.platform === "win32" ? "aia-backend.exe" : "aia-backend";
    const dir = path.join(process.resourcesPath, "aia-backend");
    return { cmd: path.join(dir, name), args: [], cwd: dir };
  }
  return { cmd: pythonPath(), args: ["backend/main.py"], cwd: ROOT };
}

function spawnSidecar() {
  const launch = sidecarLaunch();
  sidecar = spawn(launch.cmd, launch.args, {
    cwd: launch.cwd,
    env: { ...process.env, PYTHONUNBUFFERED: "1", AIA_USER_DATA: userDataDir() },
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true,
  });
  sidecar.stdout.on("data", (buf) => {
    const text = buf.toString();
    console.log("[sidecar]", text.trimEnd());
    if (text.toLowerCase().includes("websocket listening")) {
      connectWs();
    }
  });
  sidecar.stderr.on("data", (buf) => {
    console.error("[sidecar]", buf.toString().trimEnd());
  });
  sidecar.on("exit", (code, signal) => {
    console.error("sidecar exit", code, signal);
    sidecar = null;
    sendBackendState({ connected: false });
  });
}

function killSidecar() {
  if (!sidecar) return;
  const child = sidecar;
  sidecar = null;
  if (process.platform === "win32" && child.pid) {
    spawn("taskkill", ["/pid", String(child.pid), "/T", "/F"], { windowsHide: true });
  } else {
    child.kill("SIGTERM");
  }
}

function overlayBounds() {
  const area = screen.getPrimaryDisplay().workArea;
  const width = Math.max(640, area.width - 32);
  const height = Math.max(420, Math.round(area.height * 0.78));
  return {
    x: Math.round(area.x + (area.width - width) / 2),
    y: Math.round(area.y + (area.height - height) / 2),
    width,
    height,
  };
}

function pinOverlayOnTop() {
  if (!overlay || overlay.isDestroyed()) return;
  overlay.setAlwaysOnTop(true, "screen-saver", 1);
  overlay.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  overlay.moveTop();
}

function createOverlay(cfg) {
  overlay = new BrowserWindow({
    ...overlayBounds(),
    minWidth: 640,
    minHeight: 320,
    frame: false,
    transparent: true,
    hasShadow: false,
    skipTaskbar: false,
    alwaysOnTop: true,
    fullscreenable: false,
    resizable: true,
    backgroundColor: "#00000000",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
    },
  });
  pinOverlayOnTop();
  overlay.setBounds(overlayBounds());
  if (cfg.content_protection !== false) {
    overlay.setContentProtection(true);
  }
  const opacity = Number(cfg.opacity);
  overlay.setOpacity(Number.isFinite(opacity) ? opacity : 0.92);
  const hotkeys = registerHotkeys(cfg);
  overlay.webContents.on("did-finish-load", () => {
    sendBackendState({ connected: !!(ws && ws.readyState === WebSocket.OPEN) });
    if (lastStatus) overlay.webContents.send("ws-event", lastStatus);
    if (!hotkeys.okPanic) {
      overlay.webContents.send("ws-event", {
        type: "error",
        payload: {
          code: "HOTKEY_FAILED",
          message: "Panic hotkey failed to register",
          fatal: false,
        },
      });
    }
  });
  overlay.loadFile(path.join(__dirname, "renderer", "overlay.html"));
}

function openAux(name, file, size) {
  if (aux[name] && !aux[name].isDestroyed()) {
    aux[name].show();
    aux[name].focus();
    return;
  }
  aux[name] = new BrowserWindow({
    width: size && size[0] ? size[0] : 640,
    height: size && size[1] ? size[1] : 520,
    title: name,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
    },
  });
  aux[name].webContents.on("did-finish-load", () => {
    sendBackendState({ connected: !!(ws && ws.readyState === WebSocket.OPEN) });
    if (lastStatus) aux[name].webContents.send("ws-event", lastStatus);
    if (lastContext) aux[name].webContents.send("ws-event", lastContext);
    if (lastHistory) aux[name].webContents.send("ws-event", lastHistory);
  });
  aux[name].loadFile(path.join(__dirname, "renderer", file));
  aux[name].on("closed", () => {
    aux[name] = null;
  });
}

function applyOverlayPatch(patch) {
  const o = patch && patch.overlay;
  if (!o || !overlay || overlay.isDestroyed()) return;
  if (typeof o.content_protection === "boolean") overlay.setContentProtection(o.content_protection);
  if (typeof o.opacity === "number") overlay.setOpacity(o.opacity);
  if (typeof o.always_on_top === "boolean") {
    if (o.always_on_top) pinOverlayOnTop();
    else overlay.setAlwaysOnTop(false);
  }
  if (o.hotkey_toggle_visibility || o.hotkey_panic_hide) {
    globalShortcut.unregisterAll();
    const merged = { ...loadOverlayConfig(), ...o };
    const result = registerHotkeys(merged);
    const warn = [];
    if (!result.okToggle) warn.push("Toggle hotkey failed to register");
    if (!result.okPanic) warn.push("Panic hotkey failed to register");
    sendToRenderers("hotkey-warning", warn.join(". "));
  }
}

function registerHotkeys(cfg) {
  const toggle = cfg.hotkey_toggle_visibility || "CommandOrControl+Shift+H";
  const panic = cfg.hotkey_panic_hide || "CommandOrControl+Shift+Escape";
  const okToggle = globalShortcut.register(toggle, () => {
    if (!overlay || overlay.isDestroyed()) return;
    if (overlay.isVisible()) overlay.hide();
    else overlay.show();
  });
  const okPanic = globalShortcut.register(panic, () => {
    if (!overlay || overlay.isDestroyed()) return;
    overlay.hide();
  });
  if (!okToggle) console.error("failed to register toggle hotkey", toggle);
  if (!okPanic) console.error("failed to register panic hotkey", panic);
  return { okToggle, okPanic };
}

function registerIpc() {
  ipcMain.on("ws-send", (_e, msg) => {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    const raw = typeof msg === "string" ? msg : JSON.stringify(msg);
    ws.send(raw);
    if (msg && msg.type === "update_config") applyOverlayPatch(msg.payload);
  });
  ipcMain.on("hide-overlay", () => {
    if (overlay && !overlay.isDestroyed()) overlay.hide();
  });
  ipcMain.on("show-overlay", () => {
    if (overlay && !overlay.isDestroyed()) {
      overlay.setBounds(overlayBounds());
      overlay.show();
      pinOverlayOnTop();
      overlay.focus();
    }
    if (aux.Setup && !aux.Setup.isDestroyed()) {
      aux.Setup.close();
    }
  });
  ipcMain.handle("open-resume-dialog", async () => {
    const parent = aux.Setup && !aux.Setup.isDestroyed() ? aux.Setup : overlay;
    const r = await dialog.showOpenDialog(parent, {
      properties: ["openFile"],
      filters: [{ name: "Resume", extensions: ["pdf", "txt", "md"] }],
    });
    if (r.canceled || !r.filePaths[0]) return null;
    return r.filePaths[0];
  });
  ipcMain.handle("get-config", () => loadFullConfig());
  ipcMain.on("open-setup", () => openAux("Setup", "setup.html", [640, 520]));
  ipcMain.on("open-history", () => openAux("History", "history.html", [640, 520]));
  ipcMain.on("open-settings", () => openAux("Settings", "settings.html", [720, 720]));
}

app.whenReady().then(() => {
  const cfg = loadOverlayConfig();
  registerIpc();
  createOverlay(cfg);
  spawnSidecar();
  connectWs();
});

app.on("before-quit", () => {
  quitting = true;
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  if (ws && ws.readyState === WebSocket.OPEN) {
    try {
      ws.send(JSON.stringify({ type: "stop_listening" }));
    } catch {
      /* ignore */
    }
    try {
      ws.close();
    } catch {
      /* ignore */
    }
  }
  ws = null;
  killSidecar();
  globalShortcut.unregisterAll();
});

app.on("window-all-closed", () => {
  app.quit();
});
