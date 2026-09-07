# Implementation plans

I'm using the writing-plans skill. These plans implement the specs in [`../specs/`](../specs/README.md).

**Rule:** implement **one phase at a time**, in order. Do not start Phase N until Phase N−1 acceptance in [`../specs/08-acceptance-criteria.md`](../specs/08-acceptance-criteria.md) passes.

| Phase | Plan | Deliverable |
|---|---|---|
| 1 | [phase-01-audio-capture.md](phase-01-audio-capture.md) | Config loader + loopback capture + WAV dump |
| 2 | [phase-02-stt-pipeline.md](phase-02-stt-pipeline.md) | Local STT → console transcripts |
| 3 | [phase-03-question-detection-llm.md](phase-03-question-detection-llm.md) | Detector + context + Claude streaming to console |
| 4 | [phase-04-websocket-bridge.md](phase-04-websocket-bridge.md) | Local WS service, full event contract |
| 5 | [phase-05-electron-overlay.md](phase-05-electron-overlay.md) | Overlay window, capture exclusion, live render |
| 6 | [phase-06-context-setup-ui.md](phase-06-context-setup-ui.md) | Resume/JD setup UI wired into prompts |
| 7 | [phase-07-polish-packaging.md](phase-07-polish-packaging.md) | History, settings, hotkey polish, packaging |

Roadmap and dependencies: [00-roadmap.md](00-roadmap.md).

For agentic workers executing a phase: use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans, **only for the current phase file**.
