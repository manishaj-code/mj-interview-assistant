# Acceptance Criteria — AI Interview Assistant

Use this to decide a phase is finished. Do not start the next phase until the current phase’s checks pass.

## Phase 1 — Audio capture

- `python -m pytest backend/tests/test_config_loader.py backend/tests/test_audio_capture.py` passes.
- On a machine with loopback, `python backend/audio/wav_dump.py --seconds 5` writes a `.wav` that plays back system audio (not mic-only).
- Missing device raises `AUDIO_DEVICE_NOT_FOUND` (tested with a fake device id).

## Phase 2 — STT

- Tests for `Transcriber` pass with a fake engine (no model download in CI).
- Manual: play speech to loopback, console prints partial then final lines.
- Empty audio does not print spam empty strings.

## Phase 3 — Question detection + LLM

- Detector tests: silence + question-word → detect; statement + no silence → no detect; duplicate within 5 s ignored.
- LLM client tests: fake stream yields tokens; timeout raises `LLM_TIMEOUT`.
- Manual with API key: a spoken question prints streamed tokens then a complete answer. Resume/JD can be passed as CLI args.

## Phase 4 — WebSocket bridge

- Contract tests: parse/make JSON for every v1 type.
- `websockets` client can `start_listening` and receive `status`.
- Pipeline events `transcript_*`, `question_detected`, `answer_token`, `answer_complete` match [05-websocket-contract.md](05-websocket-contract.md).
- Unknown command → `error` `UNKNOWN_COMMAND`.
- Server listens on `127.0.0.1` only.

## Phase 5 — Electron overlay

- Overlay window is transparent, always on top, draggable, resizable.
- `setContentProtection(true)` is called when config says so. Manual: window absent from OS screen-share picker / captured frames (Windows/macOS).
- Tokens append live. Start/Stop sends WS commands. Reconnect after killing sidecar.
- Panic/toggle hotkeys work while another app is focused.

## Phase 6 — Context + Setup UI

- PDF and `.txt` resume extract into `update_context`.
- JD textarea persists and appears in the next LLM prompt (verified by a logged system/user preview at `debug` or by answer content).
- Missing API key blocks Start and shows Setup banner.

## Phase 7 — Polish + packaging

- Settings persist in userData `config.json`.
- History lists Q&A after a session; disabling history writes nothing.
- Cloud STT fallback warning when Deepgram key missing.
- Windows installer (or unpackaged `electron .` + PyInstaller sidecar) launches overlay + backend together.

## Product MVP (all phases)

Meets [01-product-requirements.md](01-product-requirements.md) §7.
