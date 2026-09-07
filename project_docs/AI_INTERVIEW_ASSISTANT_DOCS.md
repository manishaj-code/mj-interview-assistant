# AI Interview Assistant — Technical Documentation

## 1. Overview

A desktop application that listens to a live video call (Zoom, Google Meet, Microsoft Teams, etc.), transcribes the interviewer's speech in real time, and generates a suggested answer using an LLM. The answer is displayed on a transparent, always-on-top overlay window that is excluded from screen-share capture.

**Primary use case:** personal interview preparation / live assistance.
**Secondary goal:** structured well enough to become a sellable SaaS product later.

**Target platform:** Desktop app — Electron (UI shell) + Python (backend service).

---

## 2. High-Level Architecture

```
┌───────────────────────────────────────────────────────────┐
│  ELECTRON APP (Frontend / Shell)                          │
│  - Transparent, always-on-top overlay window               │
│  - Screen-capture-exclusion (setContentProtection)          │
│  - Settings UI (resume upload, JD input, hotkeys)          │
│  - Renders streamed transcript + AI answer                  │
└───────────────────────┬───────────────────────────────────┘
                         │ WebSocket (localhost)
┌───────────────────────▼───────────────────────────────────┐
│  PYTHON BACKEND (Local service, runs alongside app)        │
│  ├─ Audio Capture Module      (system loopback audio)      │
│  ├─ STT Module                (faster-whisper, streaming)  │
│  ├─ Question Detection Module (VAD + boundary heuristics)  │
│  ├─ Context Manager           (resume, JD, chat history)   │
│  ├─ LLM Client                (Claude API, streaming)      │
│  └─ WebSocket Server          (pushes events to Electron)  │
└───────────────────────────────────────────────────────────┘
```

**Data flow (single question cycle):**

1. System audio is captured continuously in small chunks (e.g. 30ms frames).
2. Chunks are streamed to the STT engine, which emits partial + final transcripts.
3. A question-boundary detector watches the transcript stream for a completed question (silence gap + sentence-final punctuation/intonation heuristic, or an LLM-based classifier for ambiguous cases).
4. On a detected question, the Context Manager assembles a prompt: system instructions + resume + job description + recent conversation history + the new question.
5. The prompt is sent to the LLM via streaming API call.
6. Streamed tokens are pushed over WebSocket to the Electron overlay as they arrive.
7. The overlay renders the answer live, appending tokens as they stream in.

---

## 3. Tech Stack

| Layer | Technology | Notes |
|---|---|---|
| Desktop shell | Electron | Cross-platform packaging, overlay window, capture exclusion |
| Backend runtime | Python 3.11+ | Audio + ML ecosystem |
| Audio capture | `sounddevice` / `pyaudiowpatch` (Windows loopback) / BlackHole (macOS) / PulseAudio monitor (Linux) | Platform-specific; abstract behind a common interface |
| STT | `faster-whisper` (local) or Deepgram/AssemblyAI (cloud, lower latency) | Start local for cost/privacy, add cloud option later |
| VAD (voice activity detection) | `webrtcvad` or `silero-vad` | Used for question-boundary detection |
| LLM | Claude API (Anthropic), streaming enabled | Model choice configurable |
| IPC | WebSocket (`websockets` Python lib) | Localhost only, no external exposure |
| Packaging | `electron-builder` | Bundles Python backend as a sidecar process (via PyInstaller) |
| Storage | Local SQLite or flat JSON files | Session history, resume/JD storage — all local, no cloud DB needed for MVP |

---

## 4. Core Features (MVP Scope)

1. **Audio capture toggle** — start/stop listening to system audio.
2. **Live transcription display** — optional, shows what's being transcribed in real time (useful for debugging and trust).
3. **Automatic question detection** — no manual trigger needed; assistant detects when a question has been asked.
4. **Streamed AI answer** — answer appears token-by-token, not as a single blocking response.
5. **Resume + job description context** — user uploads resume (PDF/text) and pastes JD once per session; used in every prompt for personalized answers.
6. **Overlay window** — transparent, draggable, resizable, always-on-top, excluded from screen share.
7. **Show/hide hotkey** — global keyboard shortcut to instantly hide the overlay (panic button).
8. **Session history** — local log of questions + answers for post-interview review.

### Post-MVP / Stretch Features

- Coding-question mode (detects LeetCode-style questions, generates code + explanation)
- Multi-LLM support (swap between Claude models or providers)
- Answer style tuning (concise vs. detailed, STAR-format toggle for behavioral questions)
- Practice mode (mock interview using the same pipeline, offline, for rehearsal — no live call needed)
- Analytics dashboard (which question types took longest, most-used topics)

---

## 5. Module Breakdown

### 5.1 Audio Capture Module
- **Responsibility:** capture system output audio (the interviewer's voice) as a continuous stream, not the user's own microphone.
- **Platform notes:**
  - Windows: WASAPI loopback via `pyaudiowpatch`
  - macOS: requires a virtual audio driver (BlackHole) routed through the system's output; document setup steps for the user
  - Linux: PulseAudio/PipeWire monitor source
- **Output:** raw PCM audio chunks pushed into a queue for the STT module.

### 5.2 STT Module
- **Responsibility:** convert audio chunks into text, streaming partial results.
- **Engine:** `faster-whisper` running the `small` or `medium` model locally for a balance of speed/accuracy; expose a config option for cloud STT (Deepgram) for lower latency if the user has API access.
- **Output:** a stream of `{text, is_final, timestamp}` events.

### 5.3 Question Detection Module
- **Responsibility:** decide when a chunk of transcribed speech constitutes a complete question worth answering.
- **Approach (layered, cheapest check first):**
  1. Silence gap heuristic (e.g., >800ms pause after speech)
  2. Punctuation/intonation heuristic (ends in "?", or starts with question words: what/why/how/can you/tell me about)
  3. Fallback: a fast, cheap LLM call to classify "is this a complete question requiring an answer?" for ambiguous transcripts
- **Output:** finalized question text, timestamped.

### 5.4 Context Manager
- **Responsibility:** build the prompt sent to the LLM.
- **Inputs it maintains:**
  - System prompt (tone/format instructions — e.g., "answer concisely, in first person, as if speaking aloud")
  - Resume text (parsed once, cached)
  - Job description text
  - Rolling conversation history (last N Q&A pairs, to keep context coherent without blowing the context window)
- **Output:** a fully assembled message list ready for the LLM client.

### 5.5 LLM Client
- **Responsibility:** call the Claude API with streaming enabled, forward tokens to the WebSocket server as they arrive.
- **Config:** model name, max tokens, temperature — all user-configurable in settings.

### 5.6 WebSocket Server
- **Responsibility:** the bridge between Python backend and Electron frontend.
- **Events emitted:** `transcript_partial`, `transcript_final`, `question_detected`, `answer_token`, `answer_complete`, `error`.
- **Events received from frontend:** `start_listening`, `stop_listening`, `update_context` (resume/JD changes), `toggle_overlay`.

### 5.7 Electron Frontend
- **Responsibility:** render the overlay, manage window behavior, handle settings UI.
- **Key APIs:**
  - `win.setContentProtection(true)` — excludes window from screen capture (Windows/macOS)
  - `win.setAlwaysOnTop(true, 'screen-saver')` — keeps overlay above call windows
  - Global shortcut registration for show/hide
- **UI screens:** Setup (resume/JD upload), Live overlay (transcript + answer), Session history, Settings.

---

## 6. Non-Functional Requirements

- **Latency target:** question-end to first answer token < 2–3 seconds.
- **Privacy:** audio and transcripts should stay local by default; cloud calls limited to the LLM API (and optionally cloud STT if configured). No third-party analytics on conversation content.
- **Resilience:** if the LLM call fails or times out, show a clear error state in the overlay rather than hanging silently.
- **Cross-platform:** Windows and macOS as primary targets (Linux best-effort, given audio driver variability).

---

## 7. Suggested Build Order

1. **Audio capture PoC** — validate system-audio loopback on your target OS; dump captured audio to a `.wav` file to confirm it's clean.
2. **STT pipeline** — feed captured audio into `faster-whisper`, print live transcripts to console.
3. **Question detection + LLM call** — wire up detection heuristics, fire a Claude API call on detected questions, print streamed response to console.
4. **WebSocket bridge** — expose the above pipeline as a local WebSocket service emitting the events listed in §5.6.
5. **Electron overlay (minimal)** — a transparent window that connects to the WebSocket and renders streamed text. Get content-protection working early since it's the highest-risk platform API.
6. **Context Manager UI** — resume upload, JD input, wired into the backend's prompt assembly.
7. **Polish** — hotkeys, session history, settings panel, error states, packaging with `electron-builder` + PyInstaller sidecar.

---

## 8. Repository Structure (proposed)

```
ai-interview-assistant/
├── electron/
│   ├── main.js              # Electron main process, window management
│   ├── preload.js
│   ├── renderer/             # Overlay + settings UI
│   └── package.json
├── backend/
│   ├── audio/
│   │   └── capture.py        # Platform-specific loopback capture
│   ├── stt/
│   │   └── transcriber.py    # faster-whisper wrapper, streaming
│   ├── detection/
│   │   └── question_detector.py
│   ├── context/
│   │   └── context_manager.py
│   ├── llm/
│   │   └── claude_client.py  # Streaming API calls
│   ├── server/
│   │   └── ws_server.py      # WebSocket bridge
│   ├── main.py                # Backend entrypoint, wires all modules together
│   └── requirements.txt
├── docs/
│   └── AI_INTERVIEW_ASSISTANT_DOCS.md   # this file
└── README.md
```

---

## 9. Open Decisions to Resolve During Build

- Local Whisper model size vs. cloud STT (cost/latency/accuracy tradeoff)
- Exact silence-gap threshold for question-boundary detection (tune empirically)
- How much conversation history to keep in context (token budget vs. coherence)
- Whether macOS BlackHole setup is acceptable friction for v1, or whether a bundled virtual-audio-driver installer is needed
