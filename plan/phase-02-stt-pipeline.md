# Phase 2: STT Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Stop after this phase.** Requires Phase 1 complete. Do not start Phase 3.

**Goal:** Convert loopback PCM into partial and final transcript events; print them to the console.

**Architecture:** `Transcriber` consumes `AudioChunk` and yields `TranscriptEvent`. Local engine is `faster-whisper` (`small`). Tests use a fake engine so CI does not download models.

**Tech Stack:** faster-whisper, numpy, pytest-asyncio

**Spec:** [specs/03-module-specifications.md](../specs/03-module-specifications.md) §3, [specs/01-product-requirements.md](../specs/01-product-requirements.md) F2, [specs/08-acceptance-criteria.md](../specs/08-acceptance-criteria.md) Phase 2

## Global Constraints

- `TranscriptEvent(text: str, is_final: bool, timestamp_ms: int)`
- `Transcriber.process_chunk(chunk) -> TranscriptEvent | None`
- Empty/whitespace-only text is not emitted
- Local model size from config; default `small`
- Whisper inference in `asyncio.to_thread`
- Do not implement cloud Deepgram in this phase

---

## File map

- Create: `backend/stt/transcriber.py`
- Create: `backend/stt/__init__.py`
- Create: `backend/run_stt_console.py`
- Test: `backend/tests/test_transcriber.py`
- Modify: `backend/requirements.txt`

---

### Task 1: TranscriptEvent + fake transcriber

**Files:**
- Create: `backend/stt/transcriber.py`
- Test: `backend/tests/test_transcriber.py`

**Interfaces:**
- Consumes: `AudioChunk`, `SttConfig`
- Produces: `TranscriptEvent`, `Transcriber.start/stop/process_chunk`

- [ ] **Step 1: Write the failing tests**

```python
import asyncio

import pytest

from backend.audio.capture import AudioChunk
from backend.config.schema import SttConfig
from backend.stt.transcriber import Transcriber, TranscriptEvent


def _chunk(text_marker: bytes = b"\x00\x01"):
    pcm = (text_marker * 480)[:960]  # 30ms at 16k s16le = 960 bytes
    if len(pcm) < 960:
        pcm = pcm + b"\x00" * (960 - len(pcm))
    return AudioChunk(pcm=pcm, sample_rate=16000, timestamp_ms=1_700_000_000_000)


@pytest.mark.asyncio
async def test_fake_emits_partial_then_final():
    cfg = SttConfig(engine="local", local_model_size="small", cloud_provider=None)
    t = Transcriber(cfg, engine_impl="fake")
    await t.start()
    events = []
    for _ in range(12):
        ev = await t.process_chunk(_chunk())
        if ev:
            events.append(ev)
    await t.stop()
    assert any(e.is_final is False for e in events)
    assert any(e.is_final is True for e in events)
    assert all(e.text.strip() for e in events)
    assert all(isinstance(e, TranscriptEvent) for e in events)


@pytest.mark.asyncio
async def test_fake_does_not_emit_empty():
    cfg = SttConfig(engine="local", local_model_size="small", cloud_provider=None)
    t = Transcriber(cfg, engine_impl="fake_silence")
    await t.start()
    ev = await t.process_chunk(_chunk())
    await t.stop()
    assert ev is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_transcriber.py -v`

Expected: FAIL import `Transcriber`.

- [ ] **Step 3: Write Transcriber with fake engines**

```python
@dataclass(frozen=True)
class TranscriptEvent:
    text: str
    is_final: bool
    timestamp_ms: int

class Transcriber:
    def __init__(self, config: SttConfig, engine_impl: str = "auto"): ...
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def process_chunk(self, chunk: AudioChunk) -> TranscriptEvent | None: ...
```

- `engine_impl="fake"`: count chunks; every 3rd chunk emit partial `"hello"`, every 10th emit final `"hello world"` using the chunk timestamp
- `engine_impl="fake_silence"`: always `None`
- `engine_impl="auto"`: real whisper (Task 2); if called in this task, `start` may no-op until Task 2
- Strip whitespace; never return empty text

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest backend/tests/test_transcriber.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/stt backend/tests/test_transcriber.py
git commit -m "feat: add Transcriber interface with fake streaming events"
```

---

### Task 2: faster-whisper local engine

**Files:**
- Modify: `backend/stt/transcriber.py`
- Modify: `backend/requirements.txt`

**Interfaces:**
- Consumes: PCM buffer of ~1s windows
- Produces: partial (optional) and final `TranscriptEvent` from Whisper

- [ ] **Step 1: Add dependency**

Append to `backend/requirements.txt`:

```
faster-whisper==1.1.0
```

Run: `pip install -r backend/requirements.txt`

- [ ] **Step 2: Implement local path**

When `engine_impl=="auto"` and `config.engine=="local"`:
- On `start()`, load `WhisperModel(config.local_model_size, device="cpu", compute_type="int8")` inside `asyncio.to_thread`
- Buffer incoming PCM. Every ~1.0 s of audio (or on `stop`), run `model.transcribe` on the window with `beam_size=1`, `vad_filter=True`
- If result text is non-empty: emit `TranscriptEvent(text=..., is_final=True, timestamp_ms=chunk.timestamp_ms)`
- Optionally emit a partial with the same text and `is_final=False` immediately before the final (keeps overlay useful)
- On load failure: raise `RuntimeError` with message usable as `STT_INIT_FAILED` (Phase 4 will map the code)

Do not call network APIs.

- [ ] **Step 3: Keep fake tests green**

Run: `python -m pytest backend/tests/test_transcriber.py -v`

Expected: PASS (fake path unchanged)

- [ ] **Step 4: Commit**

```bash
git add backend/stt/transcriber.py backend/requirements.txt
git commit -m "feat: transcribe local PCM with faster-whisper small"
```

---

### Task 3: Console pipeline audio → STT

**Files:**
- Create: `backend/run_stt_console.py`

**Interfaces:**
- Consumes: `AudioCapture` + `Transcriber` + `load_config`
- Produces: stdout lines `PARTIAL:` / `FINAL:`

- [ ] **Step 1: Write console runner**

```python
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1].parent))

from backend.audio.capture import AudioCapture
from backend.config.loader import load_config
from backend.stt.transcriber import Transcriber


async def main() -> None:
    cfg = load_config(Path("backend/config/defaults.json"), Path("data/config.json"), Path(".env"))
    q: asyncio.Queue = asyncio.Queue()
    cap = AudioCapture(cfg.audio, source="loopback")
    tr = Transcriber(cfg.stt, engine_impl="auto")
    await tr.start()
    cap.start(q)
    print("listening. Ctrl+C to stop.")
    try:
        while True:
            chunk = await q.get()
            ev = await tr.process_chunk(chunk)
            if ev is None:
                continue
            tag = "FINAL" if ev.is_final else "PARTIAL"
            print(f"{tag}: {ev.text}")
    except KeyboardInterrupt:
        pass
    finally:
        cap.stop()
        await tr.stop()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Manual verification**

Play spoken audio on the machine. Run:

```
python backend/run_stt_console.py
```

Expected: `PARTIAL` and `FINAL` lines with recognizable words. Silence does not print empty lines.

- [ ] **Step 3: Commit**

```bash
git add backend/run_stt_console.py
git commit -m "feat: print live transcripts from loopback audio"
```

---

## Phase 2 acceptance

- [ ] `python -m pytest backend/tests/test_transcriber.py -v` passes without downloading a model (fake engine)
- [ ] Console runner shows live transcripts from system audio
- [ ] Empty audio does not spam blank lines

**Stop here. Do not implement question detection or LLM.**
