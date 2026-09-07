# AI Interview Assistant — Specifications Index

This folder is the requirement source of truth for implementation.  
Source inputs: `project_docs/AI_INTERVIEW_ASSISTANT_DOCS.md`, `project_docs/CONFIG_SPEC.md`, `project_docs/WEBSOCKET_EVENT_CONTRACT.md`.

Implementation must follow these specs. If code must differ, update the matching spec in the same change.

## Documents

| File | Purpose |
|---|---|
| [01-product-requirements.md](01-product-requirements.md) | Product goals, users, MVP vs out-of-scope, functional requirements |
| [02-system-architecture.md](02-system-architecture.md) | Architecture, data flow, tech stack, repo layout, locked decisions |
| [03-module-specifications.md](03-module-specifications.md) | Module responsibilities, interfaces, error codes |
| [04-configuration.md](04-configuration.md) | Env vars, `config.json`, load order, validation |
| [05-websocket-contract.md](05-websocket-contract.md) | Localhost WebSocket commands and events |
| [06-ui-requirements.md](06-ui-requirements.md) | Screens, overlay behavior, hotkeys |
| [07-non-functional-requirements.md](07-non-functional-requirements.md) | Latency, privacy, platforms, resilience |
| [08-acceptance-criteria.md](08-acceptance-criteria.md) | Phase-level done criteria |

## Implementation plans

Phased plans live in [`../plan/`](../plan/README.md). Implement **one phase at a time**, in order.

## Scope lock

- **In scope (MVP):** local system-audio capture, local STT, automatic question detection, streamed Claude answers, resume/JD context, capture-excluded overlay, show/hide hotkeys, local session history.
- **Out of scope (post-MVP):** coding-question mode, multi-LLM providers, practice/mock mode, analytics dashboard, bundled macOS virtual-audio installer.
