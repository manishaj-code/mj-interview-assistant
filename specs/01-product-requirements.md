# Product Requirements — AI Interview Assistant

## 1. Product

A desktop app that captures **system output audio** from a live video call, transcribes the interviewer's speech, detects completed questions, and streams an LLM-suggested answer into a transparent always-on-top overlay that is excluded from screen-share capture.

**Primary use:** personal interview preparation and live assistance.  
**Secondary goal:** structure the MVP so a later SaaS product is possible. SaaS, accounts, cloud storage, and billing are **out of scope**.

## 2. Users

| User | Need |
|---|---|
| Candidate (primary) | Hear interviewer questions, see a suggested spoken-style answer quickly, hide the overlay instantly |
| Same user after the call | Review local Q&A history |

Single-user, local machine. No multi-user, no accounts.

## 3. Platforms

| Platform | Status |
|---|---|
| Windows 10/11 | Primary |
| macOS | Primary, with documented BlackHole (or equivalent virtual audio device) setup |
| Linux | Best-effort (PulseAudio/PipeWire monitor). Not a release blocker. |

## 4. MVP features (in)

| ID | Feature | Requirement |
|---|---|---|
| F1 | Audio capture toggle | User can start and stop listening to system loopback audio. Microphone of the local user is not the capture source. |
| F2 | Live transcription | Overlay can show partial and final transcript text while listening. |
| F3 | Automatic question detection | A completed interviewer question is detected without a manual trigger. |
| F4 | Manual answer request | User can force an answer from the current transcript buffer if auto-detection misses a question. |
| F5 | Streamed AI answer | Answer tokens render as they arrive. The UI must not wait for the full response. |
| F6 | Resume + JD context | User uploads a resume (PDF or text) and pastes a job description once per session. Both are included in every answer prompt. |
| F7 | Overlay window | Transparent, draggable, resizable, always-on-top, excluded from screen capture by default. |
| F8 | Show/hide hotkeys | Global shortcut toggles overlay visibility. Separate panic hotkey hides immediately. |
| F9 | Session history | Local log of questions + full answers for post-interview review. Can be disabled. |
| F10 | Settings | User can change LLM, STT, detection, overlay, and storage preferences. Secrets stay in `.env`. |
| F11 | Error states | Overlay shows a clear error for device, STT, LLM, timeout, and config failures. It must not hang silently. |

## 5. Out of scope (post-MVP)

- Coding-question mode (LeetCode-style generation)
- Multi-LLM / multi-provider switching beyond Anthropic Claude
- Answer-style as a product “mode switch” beyond the three system-prompt templates already in config (`concise` / `detailed` / `star_format`)
- Practice / mock interview mode (no live call)
- Analytics dashboard
- Bundled macOS virtual-audio-driver installer
- Cloud accounts, sync, or remote WebSocket exposure

## 6. User flows

### 6.1 First-run setup

1. User launches the app.
2. If `ANTHROPIC_API_KEY` is missing, show Setup and block Live until the key exists in `.env`.
3. User pastes or uploads resume; user pastes job description.
4. User confirms overlay hotkeys and content-protection default (on).
5. User starts listening.

### 6.2 Live question cycle

1. User is in a video call. System audio (interviewer) is captured.
2. Partial transcripts appear in the overlay (if live transcript is enabled).
3. Detector marks a complete question.
4. Overlay shows the question and streams the answer token-by-token.
5. On `answer_complete`, the Q&A pair is stored locally if history is enabled.

### 6.3 Panic hide

1. User presses the panic hotkey.
2. Overlay hides immediately. Listening may continue in the background; hiding is a window action, not a pipeline stop.
3. Toggle hotkey shows the overlay again.

### 6.4 Stop

1. User stops listening from the overlay/settings.
2. Pipeline returns to `idle`. No further STT/LLM work until start.

## 7. Success definition (MVP)

The product is done when a Windows user can:

1. Capture system audio from a call or local playback.
2. See a live transcript of that audio.
3. Receive a streamed, resume-aware answer within the latency target after a detected question.
4. Hide the overlay with a global hotkey.
5. Confirm the overlay is not visible in a screen share (content protection on).
6. Review the session Q&A locally after stopping.
