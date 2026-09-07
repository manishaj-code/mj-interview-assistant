# Non-Functional Requirements — AI Interview Assistant

## 1. Latency

| Metric | Target |
|---|---|
| Question-end to first `answer_token` | < 3000 ms typical on Windows, local Whisper `small`, Claude streaming |
| Overlay token append | < 50 ms after WS message |
| Panic hide | < 100 ms after keydown |

No hard fail of the build if network LLM latency exceeds 3 s; emit `LLM_TIMEOUT` at 30 s to first token.

## 2. Privacy

- Audio, transcripts, resume, JD, and history stay on the local machine by default.
- Network calls allowed: Anthropic API; Deepgram only when cloud STT is enabled.
- Bind WebSocket to `127.0.0.1` only.
- No analytics, crash-telemetry of conversation content, or third-party logging of transcripts.
- `storage.session_history_enabled: false` must not write Q&A to disk.
- `.env` is gitignored. Never copy API keys into `config.json`, logs, or overlay UI.

## 3. Resilience

- LLM failure: overlay error banner, pipeline stays `listening`.
- Missing loopback device: error banner, state `error` until Start succeeds.
- Sidecar crash: Electron reconnects (see WS contract). Overlay shows “Backend disconnected”.
- Whisper init failure: `STT_INIT_FAILED`, do not hang Start button; re-enable Start.

## 4. Security

- No remote origins in Electron (`webSecurity` left on). Load local files only.
- `nodeIntegration: false`, `contextIsolation: true`, preload-only API.
- Path in `extract_resume` must be a user-selected file. Main process should pass the path from the Open dialog, not a free-typed remote URL.

## 5. Packaging (Phase 7)

- `electron-builder` NSIS (Windows) and DMG (macOS).
- Python sidecar via PyInstaller one-folder, spawned by main.
- User data in Electron `userData`. Whisper model cache in userData.

## 6. Logging

- Backend: stderr/stdout with `LOG_LEVEL`. Default `info`.
- `debug` may log transcript text. `info` logs event types and error codes, not full answers.
- Do not log API keys.

## 7. Accessibility (MVP minimum)

- Overlay text contrast against the dark panel ≥ WCAG AA for the answer body.
- Start/Stop and Hide are keyboard-clickable when the overlay is focused.
- Global hotkeys work without overlay focus.
