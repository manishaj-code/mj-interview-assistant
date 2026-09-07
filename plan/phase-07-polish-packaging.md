# Phase 7: Polish and Packaging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Stop after this phase.** Requires Phase 6 complete. This is the last MVP phase.

**Goal:** Session history, Settings UI, cloud STT fallback warning, hotkey persistence, and packaged sidecar launch.

**Architecture:** SQLite `SessionStore` (already stubbed in Phase 4) is completed and listed via `list_history`. Settings sends `update_config`. Deepgram path is optional; missing key falls back to local with `STT_CLOUD_FALLBACK`. electron-builder + PyInstaller spawn the sidecar from `userData`/resources.

**Tech Stack:** SQLite stdlib, Deepgram SDK only if cloud path is built, electron-builder, PyInstaller

**Spec:** [specs/01-product-requirements.md](../specs/01-product-requirements.md) F8 F9 F10, [specs/04-configuration.md](../specs/04-configuration.md), [specs/06-ui-requirements.md](../specs/06-ui-requirements.md) §3–5, [specs/07-non-functional-requirements.md](../specs/07-non-functional-requirements.md) §5, [specs/08-acceptance-criteria.md](../specs/08-acceptance-criteria.md) Phase 7

## Global Constraints

- History disable = no Q&A disk writes
- Settings never writes `.env`
- Port changes require app restart; live `update_config` of `server.port` emits `CONFIG_INVALID` and does not bind a new port
- Cloud STT without `DEEPGRAM_API_KEY` → local + warning `STT_CLOUD_FALLBACK`
- No coding-question mode, no multi-LLM provider, no practice mode, no analytics, no bundled BlackHole installer

---

## File map

- Modify: `backend/storage/session_store.py`
- Test: `backend/tests/test_session_store.py`
- Create: `backend/stt/deepgram_engine.py` (optional cloud)
- Test: `backend/tests/test_config_loader.py` (already has cloud fallback; keep green)
- Create: `electron/renderer/history.html`
- Create: `electron/renderer/history.js`
- Create: `electron/renderer/settings.html`
- Create: `electron/renderer/settings.js`
- Modify: `electron/main.js` (userData config path, shortcuts from config, packaged sidecar)
- Create: `electron/electron-builder.yml`
- Modify: `backend/main.py` (userData config path via env `AIA_USER_DATA`)

---

### Task 1: Session history store + History UI

**Files:**
- Modify: `backend/storage/session_store.py`
- Test: `backend/tests/test_session_store.py`
- Create: `electron/renderer/history.html`
- Create: `electron/renderer/history.js`

**Interfaces:**
- Consumes: `append`, `list_history` command
- Produces: `history_data` event; History screen

- [ ] **Step 1: Write failing store tests**

```python
from backend.storage.session_store import SessionStore


def test_append_and_list(tmp_path):
    p = tmp_path / "s.sqlite"
    s = SessionStore(str(p), enabled=True)
    sid = s.start_session()
    s.append("Q?", "A.", timestamp_ms=1, duration_ms=10)
    sessions = s.list_sessions()
    assert sessions[0]["id"] == sid
    entries = s.list_entries(sid)
    assert entries[0].question_text == "Q?"
    assert entries[0].full_answer == "A."
    s.close()


def test_disabled_writes_nothing(tmp_path):
    p = tmp_path / "s.sqlite"
    s = SessionStore(str(p), enabled=False)
    s.start_session()
    s.append("Q?", "A.", timestamp_ms=1, duration_ms=10)
    s.close()
    assert not p.exists() or p.stat().st_size == 0 or SessionStore(str(p), True).list_sessions() == []
```

If disabled, **do not create** the sqlite file.

- [ ] **Step 2: Implement schema exactly as module spec; tests pass**

- [ ] **Step 3: Pipeline on `answer_complete` calls `store.append`**

Wire if not already done in Phase 4. `list_history` returns sessions newest first with nested entries.

- [ ] **Step 4: History window**

On load send `list_history`. Render sessions newest first. Empty: `No session history.` Read-only. Main `open-history` loads this file.

- [ ] **Step 5: Manual + commit**

Run a question, open History, confirm Q&A. Disable history in config file, rerun, confirm no new rows.

```bash
git add backend/storage backend/tests/test_session_store.py electron/renderer/history.html electron/renderer/history.js electron/main.js
git commit -m "feat: local sqlite session history screen"
```

---

### Task 2: Settings UI + overlay config apply

**Files:**
- Create: `electron/renderer/settings.html`
- Create: `electron/renderer/settings.js`
- Modify: `electron/main.js` (re-register hotkeys, content protection, opacity)

**Interfaces:**
- Consumes: `update_config`, `list_audio_devices`
- Produces: persisted user `config.json` under Electron `userData`

- [ ] **Step 1: Settings form**

All fields in [specs/06-ui-requirements.md](../specs/06-ui-requirements.md) §4. Save → `{type:"update_config", payload: {...}}`. Toast `Saved`. Show `error.message` on failure.

Hotkey fields: click, capture next chord, store Electron accelerator string.

On mount: `list_audio_devices` to fill the device select.

- [ ] **Step 2: userData config path**

Main sets env `AIA_USER_DATA` to `app.getPath("userData")` when spawning Python. Backend `main.py` uses `Path(os.environ.get("AIA_USER_DATA", "data")) / "config.json"` as user config path.

- [ ] **Step 3: Apply overlay fields immediately**

When `update_config` succeeds, main also:
- `overlay.setContentProtection(payload.overlay.content_protection)` if present
- `overlay.setOpacity`
- `overlay.setAlwaysOnTop`
- unregister/register global shortcuts from new hotkeys; on failure send renderer a warning string (Settings shows it). Do not crash.

- [ ] **Step 4: Port-change rule**

Backend: if patch contains `server.port` or `server.host`, emit `error` `CONFIG_INVALID` `"port changes need app restart"` and do not apply host/port live.

- [ ] **Step 5: Manual + commit**

Change answer_style to `star_format`, ask a behavioral question, confirm STAR-shaped answer. Toggle content protection off/on. Change panic hotkey and verify.

```bash
git add electron/renderer/settings.html electron/renderer/settings.js electron/main.js backend
git commit -m "feat: settings ui persisted to userData config"
```

---

### Task 3: Cloud STT option + fallback warning

**Files:**
- Modify: `backend/stt/transcriber.py`
- Create: `backend/stt/deepgram_engine.py`
- Modify: `backend/config/loader.py` (already falls back; ensure `warnings` on first status)

**Interfaces:**
- Consumes: `stt.engine == "cloud"`, `DEEPGRAM_API_KEY`
- Produces: Deepgram streaming **or** local fallback + `warnings: ["STT_CLOUD_FALLBACK"]`

- [ ] **Step 1: Status warnings**

On WS connect and `start_listening`, include `warnings` from config load. Loader should expose `stt_cloud_fallback: bool` on a small `LoadResult` **or** store it on `AppConfig` — frozen config cannot add extra fields.

**Locked:** `load_config` returns `AppConfig` only. Pipeline keeps `self.warnings: list[str]` set at init from the same fallback check (re-read env: if user json engine cloud and no deepgram key, `self.warnings = ["STT_CLOUD_FALLBACK"]`).

- [ ] **Step 2: Deepgram engine**

If engine is cloud and key exists, `Transcriber` uses Deepgram live transcription to emit `TranscriptEvent`. Tests fake this with `engine_impl="fake"`. Do not call Deepgram in pytest.

If Deepgram init fails at runtime: broadcast `STT_INIT_FAILED`, fall back to local if possible, else state `error`.

- [ ] **Step 3: Commit**

```bash
git add backend/stt backend/pipeline.py
git commit -m "feat: optional deepgram stt with local fallback warning"
```

---

### Task 4: Packaging

**Files:**
- Create: `electron/electron-builder.yml`
- Create: `backend/packaging/pyinstaller.spec` (or documented `pyinstaller` command)
- Modify: `electron/main.js` sidecar path
- Modify: `README.md` run/pack instructions

**Interfaces:**
- Consumes: packaged extraResources
- Produces: Windows NSIS (primary) and macOS DMG (if building on macOS)

- [ ] **Step 1: PyInstaller sidecar**

From repo root, one-folder build of `backend/main.py` named `aia-backend`. Include `backend/config/defaults.json`. Whisper weights download into userData on first run (document that).

- [ ] **Step 2: electron-builder**

`electron/electron-builder.yml`:
- appId `com.aia.interviewassistant`
- extraResources: the PyInstaller folder
- win: nsis
- mac: dmg (unsigned is fine for MVP)

Main spawn logic:

```javascript
const sidecar = app.isPackaged
  ? path.join(process.resourcesPath, "aia-backend", "aia-backend.exe")
  : "python";
const args = app.isPackaged ? [] : ["backend/main.py"];
```

On macOS packaged binary has no `.exe`. Use `process.platform === "win32" ? "aia-backend.exe" : "aia-backend"`.

- [ ] **Step 3: Manual packaged run**

`cd electron && npx electron-builder --dir` then launch unpacked app. Overlay + backend start together. One question cycle works.

If PyInstaller is too heavy for the machine, document the exact commands and still implement spawn-path branching; unpacked `electron .` with Python remains supported.

- [ ] **Step 4: README**

Document: Python 3.11, venv, `.env`, Windows loopback, macOS BlackHole, `npm start`, pack commands. No API keys in the file.

- [ ] **Step 5: Commit**

```bash
git add electron/electron-builder.yml electron/main.js README.md backend/packaging
git commit -m "feat: package electron app with python sidecar"
```

---

## Phase 7 / MVP acceptance

- [ ] Settings persist in userData `config.json`
- [ ] History lists Q&A; disabled history writes nothing
- [ ] Cloud STT fallback warning when Deepgram key missing
- [ ] Packaged or documented sidecar launch starts overlay + backend
- [ ] Product checks in [specs/01-product-requirements.md](../specs/01-product-requirements.md) §7 hold on Windows

**MVP complete. Do not add post-MVP features from the product spec §5.**
