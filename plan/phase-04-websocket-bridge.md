# Phase 4: WebSocket Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Stop after this phase.** Requires Phase 3 complete. Do not start Phase 5.

**Goal:** Expose the Phase 3 pipeline as a localhost WebSocket service that speaks the v1 contract.

**Architecture:** `events.py` serializes/parses JSON. `Pipeline` owns listening state. `WsServer` binds `127.0.0.1` only and broadcasts. Tests use fake capture/STT/LLM.

**Tech Stack:** websockets, pytest-asyncio

**Spec:** [specs/05-websocket-contract.md](../specs/05-websocket-contract.md), [specs/03-module-specifications.md](../specs/03-module-specifications.md) §7–8, [specs/08-acceptance-criteria.md](../specs/08-acceptance-criteria.md) Phase 4

## Global Constraints

- Bind `127.0.0.1` only; default port `8765`
- Every message has `type`; events always have `payload`
- Unknown command → `error` `UNKNOWN_COMMAND`, `fatal: false`
- Invalid JSON → `error` `UNKNOWN_COMMAND`, message `invalid json`
- `answer_token.seq` starts at 1 per answer
- `status.payload` includes `state`, `warnings`, `missing_api_key`
- Whisper/LLM stay off the asyncio loop (thread pool / async SDK)

---

## File map

- Create: `backend/server/events.py`
- Create: `backend/server/ws_server.py`
- Create: `backend/pipeline.py`
- Create: `backend/main.py`
- Create: `backend/storage/session_store.py` (no-op writes if disabled; real SQLite schema, used fully in Phase 7)
- Test: `backend/tests/test_events.py`
- Test: `backend/tests/test_pipeline_ws.py`
- Modify: `backend/requirements.txt` add `websockets==14.1`

---

### Task 1: Event codec

**Files:**
- Create: `backend/server/__init__.py`
- Create: `backend/server/events.py`
- Test: `backend/tests/test_events.py`

**Interfaces:**
- Consumes: raw JSON string or Python dict
- Produces: `make_event(type: str, payload: dict | None) -> str`, `parse_command(raw: str) -> dict`

- [ ] **Step 1: Write the failing tests**

```python
import json

import pytest

from backend.server.events import make_event, parse_command

COMMANDS = [
    "start_listening",
    "stop_listening",
    "update_context",
    "update_config",
    "manual_answer_request",
    "extract_resume",
    "list_history",
    "list_audio_devices",
]


def test_make_event_always_has_payload():
    raw = make_event("status", {"state": "idle", "warnings": [], "missing_api_key": True})
    obj = json.loads(raw)
    assert obj["type"] == "status"
    assert obj["payload"]["state"] == "idle"
    assert obj["payload"]["missing_api_key"] is True


def test_parse_commands():
    for t in COMMANDS:
        parsed = parse_command(json.dumps({"type": t}))
        assert parsed["type"] == t


def test_parse_invalid_json():
    with pytest.raises(ValueError, match="invalid json"):
        parse_command("{")


def test_parse_missing_type():
    with pytest.raises(ValueError):
        parse_command("{}")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_events.py -v`

Expected: FAIL import.

- [ ] **Step 3: Implement make_event / parse_command**

`make_event`: if payload is None, use `{}`. Return compact JSON string.  
`parse_command`: `json.loads`; on failure raise `ValueError("invalid json")`; require `type` str.

- [ ] **Step 4: Run tests**

Run: `python -m pytest backend/tests/test_events.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/server backend/tests/test_events.py
git commit -m "feat: encode and parse v1 websocket JSON messages"
```

---

### Task 2: SessionStore stub + Pipeline

**Files:**
- Create: `backend/storage/__init__.py`
- Create: `backend/storage/session_store.py`
- Create: `backend/pipeline.py`
- Test: `backend/tests/test_pipeline.py`

**Interfaces:**
- Consumes: `AppConfig`, `broadcast` callable, `SessionStore`
- Produces: Pipeline methods from the module spec

- [ ] **Step 1: Write failing pipeline tests** (fake collaborators injected)

```python
import asyncio

import pytest

from backend.config.loader import load_config
from backend.pipeline import Pipeline
from pathlib import Path


class FakeStore:
    def __init__(self):
        self.rows = []
        self.enabled = True
    def start_session(self):
        return 1
    def append(self, **kwargs):
        self.rows.append(kwargs)
    def list_sessions(self):
        return []
    def list_entries(self, session_id):
        return []
    def close(self):
        pass


@pytest.mark.asyncio
async def test_start_stop_state(tmp_path):
    events = []
    async def broadcast(msg):
        events.append(msg)
    cfg = load_config(Path("backend/config/defaults.json"), tmp_path / "no.json", None)
    p = Pipeline(cfg, broadcast, FakeStore(), collaborators="fake")
    assert p.state() == "idle"
    await p.start_listening()
    assert p.state() == "listening"
    await p.start_listening()  # no-op
    await p.stop_listening()
    assert p.state() == "idle"
    types = [e["type"] for e in events]
    assert types.count("status") >= 2


@pytest.mark.asyncio
async def test_manual_empty_buffer_errors(tmp_path):
    events = []
    async def broadcast(msg):
        events.append(msg)
    cfg = load_config(Path("backend/config/defaults.json"), tmp_path / "no.json", None)
    p = Pipeline(cfg, broadcast, FakeStore(), collaborators="fake")
    await p.manual_answer_request()
    err = [e for e in events if e["type"] == "error"][0]
    assert err["payload"]["code"] == "NO_TRANSCRIPT_BUFFER"
    assert err["payload"]["fatal"] is False
```

`collaborators="fake"` must use Phase 2/3 fake audio/STT/LLM so tests do not need hardware or API keys.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_pipeline.py -v`

Expected: FAIL import `Pipeline`.

- [ ] **Step 3: Implement SessionStore and Pipeline**

`SessionStore` as specified: create tables if enabled; if `enabled` is False, `append` is no-op.

`Pipeline`:
- `start_listening`: start capture, STT, session; set state listening; broadcast status; spawn `_run_loop` task: get chunks, `process_chunk`, broadcast transcript events, `on_transcript`/`on_silence`, on question broadcast `question_detected` then stream tokens (`seq` 1..n) then `answer_complete` and `store.append`
- Missing API key: still allow listening for transcripts, but on question broadcast `error` `MISSING_API_KEY` `fatal: false` and skip LLM
- If `question_detection.use_llm_fallback_classifier` is true, pass `classify_fn` that awaits `ClaudeClient.classify_is_question` (sync wrapper via `asyncio.run_coroutine_threadsafe` or call from the async loop only)
- `stop_listening`: stop capture, cancel LLM, state idle, status
- `update_context`: apply resume/JD keep-empty-resume rule from the WS contract; broadcast `context_updated`
- `extract_resume`: `.txt` and `.md` via UTF-8 file read into `set_resume`, then `context_updated`. `.pdf` in this phase broadcasts `error` `RESUME_PARSE_FAILED` with message `PDF extraction ships in phase 6` (`fatal: false`). Phase 6 replaces this branch with `extract_resume_text`.

- `update_config` calls `merge_user_config` and persists `data/config.json`
- `list_history` broadcasts `history_data`
- `list_audio_devices` broadcasts `audio_devices`

- [ ] **Step 4: Run tests**

Run: `python -m pytest backend/tests/test_pipeline.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/pipeline.py backend/storage backend/tests/test_pipeline.py
git commit -m "feat: pipeline start/stop and websocket-facing commands"
```

---

### Task 3: WsServer + main entry

**Files:**
- Create: `backend/server/ws_server.py`
- Create: `backend/main.py`
- Test: `backend/tests/test_pipeline_ws.py`

**Interfaces:**
- Consumes: `Pipeline`
- Produces: `ws://127.0.0.1:8765` (or free test port)

- [ ] **Step 1: Write failing WS integration test**

```python
import asyncio
import json
from pathlib import Path

import pytest
import websockets

from backend.config.loader import load_config
from backend.pipeline import Pipeline
from backend.server.ws_server import WsServer
from backend.tests.test_pipeline import FakeStore


@pytest.mark.asyncio
async def test_start_listening_status(tmp_path):
    cfg = load_config(Path("backend/config/defaults.json"), tmp_path / "no.json", None)
    # force test port
    cfg = cfg  # Pipeline uses cfg.server.port; merge port 18765 via merge_user_config
    from backend.config.loader import merge_user_config
    cfg = merge_user_config(cfg, {"server": {"port": 18765}})
    events_out = []
    async def broadcast(msg):
        events_out.append(msg)
        await server.broadcast(msg)
    store = FakeStore()
    pipeline = Pipeline(cfg, broadcast, store, collaborators="fake")
    server = WsServer(cfg.server.host, cfg.server.port, pipeline)
    await server.start()
    try:
        uri = f"ws://{cfg.server.host}:{cfg.server.port}"
        async with websockets.connect(uri) as ws:
            first = json.loads(await asyncio.wait_for(ws.recv(), timeout=2))
            assert first["type"] == "status"
            await ws.send(json.dumps({"type": "start_listening"}))
            got = json.loads(await asyncio.wait_for(ws.recv(), timeout=2))
            assert got["type"] == "status"
            assert got["payload"]["state"] == "listening"
            await ws.send(json.dumps({"type": "not_a_command"}))
            err = json.loads(await asyncio.wait_for(ws.recv(), timeout=2))
            assert err["type"] == "error"
            assert err["payload"]["code"] == "UNKNOWN_COMMAND"
    finally:
        await pipeline.stop_listening()
        await server.stop()
```

Fix circular `broadcast`/`server` in implementation: `WsServer` should call `pipeline` and use its own client set. Pipeline’s `broadcast` should be `server.broadcast`. Construct server first with a placeholder, or pass a list of clients. **Locked construction in `main.py`:**

```python
pending: list = []
async def broadcast(msg):
    await server.broadcast(msg)
server = WsServer(host, port, pipeline=None)
pipeline = Pipeline(cfg, broadcast, store)
server.pipeline = pipeline
```

Use that pattern in the test too (no FakeStore broadcast loop).

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_pipeline_ws.py -v`

Expected: FAIL import `WsServer`.

- [ ] **Step 3: Implement WsServer and main.py**

`WsServer.start`: `websockets.serve(handler, host, port)` with `host=="127.0.0.1"`. On connect: register, send `status`. On message: `parse_command`, dispatch:

| type | method |
|---|---|
| start_listening | `pipeline.start_listening` |
| stop_listening | `pipeline.stop_listening` |
| update_context | `update_context(**payload)` |
| update_config | `update_config(payload)` |
| manual_answer_request | `manual_answer_request` |
| extract_resume | `extract_resume(payload["path"])` |
| list_history | `list_history` |
| list_audio_devices | `list_audio_devices` |
| else | broadcast error UNKNOWN_COMMAND |

`main.py`: load config, build store from `cfg.storage`, build pipeline+server, `asyncio.run` forever. Log bind address at info.

- [ ] **Step 4: Run tests**

Run: `python -m pytest backend/tests/test_events.py backend/tests/test_pipeline.py backend/tests/test_pipeline_ws.py -v`

Expected: PASS

- [ ] **Step 5: Manual bind check**

Run: `python backend/main.py`  
Confirm it listens on 127.0.0.1:8765. Confirm it does not listen on 0.0.0.0.

- [ ] **Step 6: Commit**

```bash
git add backend/server/ws_server.py backend/main.py backend/tests/test_pipeline_ws.py backend/requirements.txt
git commit -m "feat: localhost websocket bridge for the interview pipeline"
```

---

## Phase 4 acceptance

- [ ] All new tests pass
- [ ] WS client can start listening and receive `status`
- [ ] Unknown command returns `UNKNOWN_COMMAND`
- [ ] Server binds loopback only

**Stop here. Do not build Electron.**
