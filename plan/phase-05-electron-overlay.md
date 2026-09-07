# Phase 5: Electron Overlay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Stop after this phase.** Requires Phase 4 complete. Do not start Phase 6.

**Goal:** Electron overlay connects to the backend, renders streamed transcript/answer, stays always-on-top, and is excluded from screen capture.

**Architecture:** Main process owns windows, shortcuts, sidecar spawn, and content protection. Preload exposes a narrow API. Renderer overlay store is a plain JS module unit-tested with Node’s test runner (no network).

**Tech Stack:** Electron 33+, vanilla HTML/CSS/JS

**Spec:** [specs/06-ui-requirements.md](../specs/06-ui-requirements.md) §1 §5 §6, [specs/07-non-functional-requirements.md](../specs/07-non-functional-requirements.md) §4, [specs/08-acceptance-criteria.md](../specs/08-acceptance-criteria.md) Phase 5

## Global Constraints

- `nodeIntegration: false`, `contextIsolation: true`
- `setContentProtection(true)` when config overlay.content_protection is true (default true)
- `setAlwaysOnTop(true, 'screen-saver')`
- Panic hotkey hides; does not stop listening
- Toggle hotkey show/hide
- Reconnect 500ms → 1s → 2s → cap 5s
- Start disabled until first `status` event
- `answer_token` seq 1 clears previous answer
- Load local files only

---

## File map

- Create: `electron/package.json`
- Create: `electron/main.js`
- Create: `electron/preload.js`
- Create: `electron/renderer/overlay.html`
- Create: `electron/renderer/overlay.css`
- Create: `electron/renderer/overlay.js`
- Create: `electron/renderer/overlayStore.js`
- Create: `electron/reconnect.js`
- Test: `electron/test/overlayStore.test.js`
- Test: `electron/test/reconnect.test.js`

---

### Task 1: Overlay store (unit tested)

**Files:**
- Create: `electron/renderer/overlayStore.js`
- Create: `electron/package.json`
- Test: `electron/test/overlayStore.test.js`

**Interfaces:**
- Consumes: WS message objects `{type, payload}`
- Produces: view state `{status, transcript, question, answer, error, startEnabled, missingApiKey}`

- [ ] **Step 1: Write package.json and failing test**

`electron/package.json`:

```json
{
  "name": "ai-interview-assistant",
  "version": "0.1.0",
  "main": "main.js",
  "scripts": {
    "start": "electron .",
    "test": "node --test test/*.test.js"
  },
  "devDependencies": {
    "electron": "^33.2.1"
  }
}
```

`electron/test/overlayStore.test.js`:

```javascript
const { test } = require("node:test");
const assert = require("node:assert/strict");
const { createStore } = require("../renderer/overlayStore");

test("status enables start", () => {
  const s = createStore();
  s.apply({ type: "status", payload: { state: "idle", warnings: [], missing_api_key: false } });
  assert.equal(s.get().startEnabled, true);
  assert.equal(s.get().status, "idle");
});

test("seq 1 clears answer then appends", () => {
  const s = createStore();
  s.apply({ type: "answer_token", payload: { token: "Hello", seq: 1 } });
  s.apply({ type: "answer_token", payload: { token: " world", seq: 2 } });
  assert.equal(s.get().answer, "Hello world");
  s.apply({ type: "answer_token", payload: { token: "New", seq: 1 } });
  assert.equal(s.get().answer, "New");
});

test("error sets banner", () => {
  const s = createStore();
  s.apply({ type: "error", payload: { code: "LLM_TIMEOUT", message: "timed out", fatal: false } });
  assert.equal(s.get().error, "timed out");
});

test("question_detected sets question", () => {
  const s = createStore();
  s.apply({ type: "question_detected", payload: { question_text: "Why us?", timestamp: 1 } });
  assert.equal(s.get().question, "Why us?");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd electron && npm install && npm test`

Expected: FAIL cannot find overlayStore.

- [ ] **Step 3: Implement overlayStore.js**

Use a UMD wrapper so Node tests can `require` it and the overlay renderer can load it via `<script src="overlayStore.js">` (no `nodeIntegration`). Export `{ createStore }` for Node and `window.OverlayStore` in the browser.

```javascript
function createStore() {
  let state = {
    status: "disconnected",
    transcript: "",
    question: "",
    answer: "",
    error: "",
    startEnabled: false,
    missingApiKey: false,
    listening: false,
  };
  function apply(msg) {
    if (!msg || !msg.type) return;
    const p = msg.payload || {};
    if (msg.type === "status") {
      state.status = p.state;
      state.startEnabled = true;
      state.missingApiKey = !!p.missing_api_key;
      state.listening = p.state === "listening";
    }
    if (msg.type === "transcript_partial" || msg.type === "transcript_final") {
      state.transcript = p.text || "";
    }
    if (msg.type === "question_detected") state.question = p.question_text || "";
    if (msg.type === "answer_token") {
      if (p.seq === 1) state.answer = "";
      state.answer += p.token || "";
    }
    if (msg.type === "answer_complete") state.answer = p.full_answer || state.answer;
    if (msg.type === "error") state.error = p.message || p.code;
  }
  function dismissError() { state.error = ""; }
  function get() { return { ...state }; }
  return { apply, get, dismissError };
}
module.exports = { createStore };
```

- [ ] **Step 4: Run tests**

Run: `cd electron && npm test`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add electron/package.json electron/renderer/overlayStore.js electron/test/overlayStore.test.js
git commit -m "feat: overlay view store for websocket events"
```

---

### Task 2: Reconnect helper

**Files:**
- Create: `electron/reconnect.js`
- Test: `electron/test/reconnect.test.js`

**Interfaces:**
- Consumes: attempt number
- Produces: delay ms: 500, 1000, 2000, 5000, 5000, ...

- [ ] **Step 1: Write failing test**

```javascript
const { test } = require("node:test");
const assert = require("node:assert/strict");
const { nextDelayMs } = require("../reconnect");

test("backoff cap 5s", () => {
  assert.equal(nextDelayMs(0), 500);
  assert.equal(nextDelayMs(1), 1000);
  assert.equal(nextDelayMs(2), 2000);
  assert.equal(nextDelayMs(3), 5000);
  assert.equal(nextDelayMs(99), 5000);
});
```

- [ ] **Step 2: Run to verify fail, implement, pass**

```javascript
function nextDelayMs(attempt) {
  const seq = [500, 1000, 2000, 5000];
  return seq[Math.min(attempt, seq.length - 1)];
}
module.exports = { nextDelayMs };
```

Run: `cd electron && npm test`

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add electron/reconnect.js electron/test/reconnect.test.js
git commit -m "feat: websocket reconnect backoff with 5s cap"
```

---

### Task 3: Main, preload, overlay UI

**Files:**
- Create: `electron/main.js`
- Create: `electron/preload.js`
- Create: `electron/renderer/overlay.html`
- Create: `electron/renderer/overlay.css`
- Create: `electron/renderer/overlay.js`

**Interfaces:**
- Consumes: `window.api.send(cmd)`, `window.api.onEvent(cb)`
- Produces: overlay window + sidecar process

- [ ] **Step 1: Implement preload.js**

```javascript
const { contextBridge, ipcRenderer } = require("electron");
contextBridge.exposeInMainWorld("api", {
  send: (msg) => ipcRenderer.send("ws-send", msg),
  onEvent: (cb) => ipcRenderer.on("ws-event", (_e, data) => cb(data)),
  onBackendState: (cb) => ipcRenderer.on("backend-state", (_e, data) => cb(data)),
  openSetup: () => ipcRenderer.send("open-setup"),
  openHistory: () => ipcRenderer.send("open-history"),
  openSettings: () => ipcRenderer.send("open-settings"),
  hideOverlay: () => ipcRenderer.send("hide-overlay"),
});
```

Setup/History/Settings windows can be empty placeholders (`about:blank` or a one-line HTML “Phase 6/7”) so buttons do not crash. Full screens are later phases.

- [ ] **Step 2: Implement main.js**

Must:
- Create overlay BrowserWindow with flags from UI spec
- `win.setContentProtection(true)`
- `win.setAlwaysOnTop(true, "screen-saver")`
- `win.setOpacity(0.92)`
- Register `CommandOrControl+Shift+H` toggle, `CommandOrControl+Shift+Escape` hide
- Spawn `python backend/main.py` with cwd = repo root, `PYTHONUNBUFFERED=1`
- Connect WebSocket to `ws://127.0.0.1:8765` using the `ws` package **or** undici/native after sidecar stdout shows bind. Add `"ws": "^8.18.0"` dependency if used from main. **Locked:** use Electron utility process or `ws` in main. Install `ws`.
- Forward inbound WS JSON to renderer via `ws-event`
- `ws-send` from renderer writes to socket
- On close, reconnect using `nextDelayMs`
- On app quit: send stop_listening if possible, kill sidecar
- Log sidecar stdout/stderr

- [ ] **Step 3: Overlay HTML/CSS/JS**

HTML: drag bar, Start, Stop, Answer now, Setup, History, Settings, Hide, status pill, transcript div, question div, answer div, error banner with dismiss.

CSS: background `rgba(16,16,20,0.85)`, light text, 28px `-webkit-app-region: drag` bar; buttons `no-drag`.

JS: `createStore()`, `window.api.onEvent` → apply → render. Start sends `{type:"start_listening"}`. Stop sends `{type:"stop_listening"}`. Answer now sends `{type:"manual_answer_request"}`. Disable Start until `startEnabled`. If `missingApiKey`, show banner from spec.

- [ ] **Step 4: Manual verification**

1. `python backend/main.py` in one terminal (or rely on spawn).
2. `cd electron && npm start`
3. Overlay appears on top, draggable, resizable.
4. Start → status listening; play speech → transcript; question → tokens append.
5. Panic hotkey hides while another app focused; toggle shows.
6. Windows: share screen in Meet/Teams/Zoom — overlay must not appear in the shared frame when content protection is on.
7. Kill Python → overlay shows disconnected (status disconnected / error); restart Python → reconnects without restarting Electron.

- [ ] **Step 5: Commit**

```bash
git add electron
git commit -m "feat: electron overlay with capture exclusion and live answers"
```

---

## Phase 5 acceptance

- [ ] Overlay unit tests pass
- [ ] Overlay is transparent, always-on-top, draggable, resizable
- [ ] Content protection called; manual screen-share check
- [ ] Tokens append live; Start/Stop work
- [ ] Hotkeys work without overlay focus
- [ ] Sidecar reconnect works

**Stop here. Do not build Setup/Settings/History screens.**
