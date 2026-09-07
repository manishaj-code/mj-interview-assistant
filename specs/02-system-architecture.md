# System Architecture — AI Interview Assistant

## 1. Locked approach

Electron desktop shell + local Python backend, connected only over `ws://127.0.0.1:<port>`.

This is the only MVP architecture. Do not introduce HTTP REST, gRPC, cloud backends, or in-process Python-in-Electron bindings.

## 2. System diagram

```
┌───────────────────────────────────────────────────────────┐
│  ELECTRON APP (Frontend / Shell)                          │
│  - Transparent, always-on-top overlay window              │
│  - Screen-capture exclusion (setContentProtection)        │
│  - Settings / Setup / History UI                          │
│  - Renders streamed transcript + AI answer                │
└───────────────────────┬───────────────────────────────────┘
                         │ WebSocket (localhost only)
┌───────────────────────▼───────────────────────────────────┐
│  PYTHON BACKEND (sidecar process)                         │
│  ├─ Config loader                                         │
│  ├─ Audio Capture                                         │
│  ├─ STT                                                   │
│  ├─ Question Detection                                    │
│  ├─ Context Manager                                       │
│  ├─ LLM Client (Anthropic streaming)                      │
│  ├─ Session store (SQLite)                                │
│  └─ WebSocket server                                      │
└───────────────────────────────────────────────────────────┘
```

Electron starts the Python sidecar. The sidecar must not be reachable from non-loopback interfaces.

## 3. Data flow (one question)

1. Capture emits PCM chunks (~30 ms) onto an `asyncio.Queue`.
2. STT consumes chunks and emits `TranscriptEvent` (`partial` then `final`).
3. Question detector consumes transcript events. On a complete question it emits `DetectedQuestion`.
4. Context manager builds an Anthropic message list: system + resume + JD + last N Q&A + new question.
5. LLM client streams tokens.
6. WebSocket server forwards events to Electron.
7. Overlay appends tokens. On complete, session store writes the pair if enabled.

## 4. Tech stack (locked)

| Layer | Choice | Rule |
|---|---|---|
| Desktop shell | Electron | Main + preload + renderer. No React/Vue requirement; vanilla HTML/CSS/JS. |
| Backend | Python 3.11+ | Single asyncio event loop. Blocking ML in a thread pool. |
| Audio Windows | `pyaudiowpatch` WASAPI loopback | Default path on Windows. |
| Audio macOS | `sounddevice` + BlackHole (user-installed) | Document setup. Do not bundle a driver installer. |
| Audio Linux | PulseAudio/PipeWire monitor via `sounddevice` | Best-effort. |
| STT default | `faster-whisper`, model size `small` | Local, privacy default. |
| STT optional | Deepgram | Only if `stt.engine == "cloud"` and `DEEPGRAM_API_KEY` is set. |
| VAD | timestamp gap via `QuestionDetector.on_silence` | MVP does not require `silero-vad` |
| LLM | Anthropic Claude streaming | Model default `claude-sonnet-4-6`. No other provider in MVP. |
| IPC | `websockets` library | JSON messages, `type` field required. |
| Config | `.env` + `config.json` | Secrets never in `config.json`. |
| Storage | SQLite | Path from config. No cloud DB. |
| PDF parse | `pypdf` | Resume upload on Setup. |
| Packaging | `electron-builder` + PyInstaller sidecar | Phase 7 only. |

## 5. Repository layout (locked)

```
ai-interview-assistant/
├── electron/
│   ├── main.js
│   ├── preload.js
│   ├── renderer/
│   │   ├── overlay.html
│   │   ├── overlay.js
│   │   ├── overlay.css
│   │   ├── setup.html
│   │   ├── setup.js
│   │   ├── history.html
│   │   ├── history.js
│   │   ├── settings.html
│   │   └── settings.js
│   └── package.json
├── backend/
│   ├── audio/
│   │   ├── capture.py
│   │   └── devices.py
│   ├── stt/
│   │   └── transcriber.py
│   ├── detection/
│   │   └── question_detector.py
│   ├── context/
│   │   ├── context_manager.py
│   │   └── pdf_extract.py
│   ├── llm/
│   │   └── claude_client.py
│   ├── server/
│   │   ├── events.py
│   │   └── ws_server.py
│   ├── storage/
│   │   └── session_store.py
│   ├── config/
│   │   ├── defaults.json
│   │   ├── loader.py
│   │   └── schema.py
│   ├── pipeline.py
│   ├── main.py
│   ├── requirements.txt
│   └── tests/
├── data/                      # runtime; gitignored except .gitkeep
├── specs/
├── plan/
├── project_docs/
├── .env.example
├── .gitignore
└── README.md
```

Do not add extra top-level packages. Put new backend code under the module that owns the behavior.

## 6. Process model

- **Electron main** owns windows, global shortcuts, content protection, and spawning `python backend/main.py`.
- **Python `main.py`** loads config, starts the WebSocket server, and runs the pipeline on `start_listening`.
- One pipeline instance per process. Starting twice is a no-op if already `listening`. Stopping when `idle` is a no-op.

## 7. Locked decisions (were open in project_docs)

| Topic | Decision |
|---|---|
| STT | Local `faster-whisper` `small` is the MVP default. Cloud Deepgram is a settings option, implemented after local STT works. |
| Silence gap | Default `800` ms, user-configurable. No extra “tuning UI” beyond Settings. |
| History window | Last `5` Q&A pairs in the prompt (`context.max_history_pairs`). |
| macOS audio | User installs BlackHole (or equivalent). App documents the steps. No bundled installer in MVP. |
| Overlay toggle over WS | Not a backend command. Show/hide is Electron-only. |
| WS bind | `127.0.0.1` only. Port default `8765`, configurable. |
| Answer style | Three system-prompt templates: `concise`, `detailed`, `star_format`. Default `concise`. |

## 8. Concurrency rules

- Audio callback must only enqueue PCM; it must not run STT or LLM.
- `faster-whisper` inference runs in `asyncio.to_thread` (or a dedicated executor).
- LLM streaming uses async Anthropic client on the main loop.
- If a new question is detected while an answer is still streaming, **cancel** the in-flight LLM stream, emit `error` with code `LLM_CANCELLED` only if a partial answer was shown, then start the new answer. Overlay replaces the in-progress answer.
