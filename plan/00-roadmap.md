# Roadmap — AI Interview Assistant

**Goal:** Ship the MVP in seven sequential phases. Each phase leaves working, testable software.

**Architecture:** Electron shell + Python sidecar, localhost WebSocket. See [specs/02-system-architecture.md](../specs/02-system-architecture.md).

**Tech stack:** Python 3.11+, Electron, faster-whisper, Anthropic Claude, SQLite.

**Spec:** [specs/README.md](../specs/README.md)

## Global constraints (all phases)

- Python 3.11+
- Bind WebSocket to `127.0.0.1` only; default port `8765`
- Secrets only in `.env`; never in `config.json`
- Default STT: local `faster-whisper` model `small`
- Default LLM: `claude-sonnet-4-6`, streaming
- Audio: 16-bit PCM mono, 16000 Hz, 30 ms chunks, system loopback (not microphone)
- Overlay excluded from screen capture by default
- No post-MVP features (coding mode, multi-provider LLM, practice mode, analytics, bundled macOS driver)
- Names and types in [specs/03-module-specifications.md](../specs/03-module-specifications.md) are locked
- Windows is the primary verification OS; macOS documented; Linux best-effort

## Phase graph

```
Phase 1 Audio  →  Phase 2 STT  →  Phase 3 Detect+LLM
                                          ↓
                                   Phase 4 WebSocket
                                          ↓
                                   Phase 5 Overlay
                                          ↓
                                   Phase 6 Setup UI
                                          ↓
                                   Phase 7 Polish
```

Do not parallelize phases. Later files assume earlier modules exist.

## How to start a phase

1. Open only that phase markdown under `plan/`.
2. Complete every checkbox. Do not skip tests.
3. Run that phase’s acceptance checks.
4. Stop. Wait for a new instruction before the next phase.
