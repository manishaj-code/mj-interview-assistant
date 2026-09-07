# UI Requirements — AI Interview Assistant

Four screens. Overlay is a separate always-on-top BrowserWindow. Setup, Settings, and History may share one normal window with simple navigation (buttons or tabs). No design-system library required.

## 1. Overlay window

**Files:** `electron/renderer/overlay.html`, `overlay.js`, `overlay.css`

### Window flags (main process)

- `transparent: true`
- `frame: false`
- `alwaysOnTop: true` with level `'screen-saver'`
- `skipTaskbar: false` (user must be able to find it)
- `hasShadow: false`
- Default size `480 x 360`, min `320 x 200`
- `win.setContentProtection(true)` when `overlay.content_protection` is true
- `win.setOpacity(config.overlay.opacity)`

### Chrome

- Drag region on a 28px top bar.
- Resize enabled.
- Controls on the top bar: Start/Stop listening, **Answer now** (sends `manual_answer_request`), Open Setup, Open History, Open Settings, Hide.
- Live transcript area (optional display; always receive events). Default: shown.
- Question line: last `question_text`.
- Answer area: appended tokens. Monospace or system UI font, high contrast on a dark semi-transparent background (`rgba(16,16,20,0.85)`).
- Status pill: `idle` / `listening` / `error`.
- Error banner: `payload.message` when `error` arrives. Dismissible. Fatal errors keep the banner until Start succeeds.

### Behavior

- On `answer_token` with `seq === 1`, clear the previous answer text.
- Append tokens in order.
- Panic hotkey: hide overlay (`win.hide()`). Do not stop listening.
- Toggle hotkey: `win.show()` / `win.hide()`.
- Drag and resize must not break content protection.

## 2. Setup screen

**Files:** `electron/renderer/setup.html`, `setup.js`

- Resume: file picker accepting `.pdf`, `.txt`, `.md`. Main sends the chosen local path with WS `extract_resume`. Backend parses via `extract_resume_text` and emits `context_updated` or `error` `RESUME_PARSE_FAILED`.
- JD: textarea; on Save send `update_context` with current `resume_text` (last extracted text kept in renderer memory) and the textarea value. Backend emits `context_updated`.
- If `status.payload.missing_api_key` is true: persistent banner “Add ANTHROPIC_API_KEY to .env and restart backend.” Live Start disabled.
- Primary button: “Continue to overlay” focuses/shows overlay.

## 3. History screen

**Files:** `electron/renderer/history.html`, `history.js`

- On load, send `list_history`.
- Group by session, newest session first.
- Each entry: timestamp (local locale string), question, full answer.
- If history disabled or empty: “No session history.”
- Read-only in MVP (no delete UI).

## 4. Settings screen

**Files:** `electron/renderer/settings.html`, `settings.js`

Editable fields matching user `config.json` except secrets:

- LLM: model (text), max_tokens, temperature, answer_style (select)
- STT: engine, local_model_size, cloud_provider
- Detection: silence_gap_ms, use_llm_fallback_classifier
- Audio: input_device (select from a device list), sample_rate (fixed 16000, display only), chunk_ms
- Overlay: always_on_top, content_protection, opacity, both hotkeys
- Storage: session_history_enabled

Device list: send `list_audio_devices`, render `audio_devices` (see [05-websocket-contract.md](05-websocket-contract.md)).

Save sends `update_config`. Show toast “Saved”. If backend replies `error`, show the message.

Hotkey capture: click field, next key chord becomes the accelerator string (Electron accelerator syntax).

## 5. Global shortcuts

Register in Electron main from config:

| Action | Default |
|---|---|
| Toggle overlay visibility | `CommandOrControl+Shift+H` |
| Panic hide | `CommandOrControl+Shift+Escape` |

If registration fails, show Settings warning; do not crash.

## 6. Sidecar lifecycle (main)

- On app ready, spawn `python backend/main.py` (or packaged binary in Phase 7).
- Log sidecar stdout/stderr to Electron log.
- On app quit, send `stop_listening` if connected, then kill sidecar.
- Overlay must wait for WS `status` before enabling Start.
