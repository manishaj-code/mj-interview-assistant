const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("api", {
  send: (msg) => ipcRenderer.send("ws-send", msg),
  onEvent: (cb) => ipcRenderer.on("ws-event", (_e, data) => cb(data)),
  onBackendState: (cb) => ipcRenderer.on("backend-state", (_e, data) => cb(data)),
  openSetup: () => ipcRenderer.send("open-setup"),
  openHistory: () => ipcRenderer.send("open-history"),
  openSettings: () => ipcRenderer.send("open-settings"),
  hideOverlay: () => ipcRenderer.send("hide-overlay"),
  showOverlay: () => ipcRenderer.send("show-overlay"),
  openResumeDialog: () => ipcRenderer.invoke("open-resume-dialog"),
  getConfig: () => ipcRenderer.invoke("get-config"),
  onHotkeyWarning: (cb) => ipcRenderer.on("hotkey-warning", (_e, data) => cb(data)),
});
