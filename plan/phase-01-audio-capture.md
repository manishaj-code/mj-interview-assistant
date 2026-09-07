# Phase 1: Audio Capture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Stop after this phase.** Do not start Phase 2 until acceptance checks pass.

**Goal:** Bootstrap the backend and capture system loopback audio into a WAV file.

**Architecture:** Python package under `backend/` with a frozen `AppConfig` loader and an `AudioCapture` that pushes `AudioChunk` PCM onto an `asyncio.Queue`. A CLI dumps five seconds to WAV to prove loopback (not microphone).

**Tech Stack:** Python 3.11+, pytest, pytest-asyncio, python-dotenv, pyaudiowpatch (Windows), sounddevice, soundfile

**Spec:** [specs/01-product-requirements.md](../specs/01-product-requirements.md) F1, [specs/02-system-architecture.md](../specs/02-system-architecture.md), [specs/03-module-specifications.md](../specs/03-module-specifications.md) §1–2, [specs/04-configuration.md](../specs/04-configuration.md), [specs/08-acceptance-criteria.md](../specs/08-acceptance-criteria.md) Phase 1

## Global Constraints

- Python 3.11+
- Audio: s16le mono, sample_rate `16000`, chunk_ms `30`
- Capture system loopback, not the default microphone
- Secrets only in `.env`
- `server.host` must be `127.0.0.1`
- Type names from the module spec are locked: `AppConfig`, `AudioChunk`, `AudioCapture`, `AudioCaptureError`

---

## File map

- Create: `.gitignore`
- Create: `.env.example`
- Create: `backend/requirements.txt`
- Create: `backend/config/defaults.json`
- Create: `backend/config/schema.py`
- Create: `backend/config/loader.py`
- Create: `backend/audio/capture.py`
- Create: `backend/audio/devices.py`
- Create: `backend/audio/wav_dump.py`
- Create: `backend/tests/test_config_loader.py`
- Create: `backend/tests/test_audio_capture.py`
- Create: `data/.gitkeep`
- Create: `README.md`

---

### Task 1: Repo scaffold

**Files:**
- Create: `.gitignore`
- Create: `.env.example`
- Create: `backend/requirements.txt`
- Create: `backend/config/__init__.py`
- Create: `backend/audio/__init__.py`
- Create: `backend/tests/__init__.py`
- Create: `data/.gitkeep`
- Create: `README.md`

**Interfaces:**
- Consumes: nothing
- Produces: installable pytest environment

- [ ] **Step 1: Write `.gitignore`**

```
.env
data/*.wav
data/*.sqlite
data/config.json
__pycache__/
*.pyc
.pytest_cache/
.venv/
node_modules/
dist/
release/
```

- [ ] **Step 2: Write `.env.example` and `backend/requirements.txt`**

`.env.example`:

```
ANTHROPIC_API_KEY=
DEEPGRAM_API_KEY=
LOG_LEVEL=info
```

`backend/requirements.txt`:

```
python-dotenv==1.0.1
pytest==8.3.4
pytest-asyncio==0.25.0
sounddevice==0.5.1
soundfile==0.13.1
numpy==2.2.1
pyaudiowpatch==0.2.12.6; sys_platform == "win32"
```

Empty `__init__.py` files for `backend/config`, `backend/audio`, `backend/tests`. `data/.gitkeep` empty.

`README.md` (minimal): how to create `.venv`, `pip install -r backend/requirements.txt`, copy `.env.example` to `.env`.

- [ ] **Step 3: Create venv and install**

Run (Windows PowerShell):

```
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
```

Expected: install succeeds.

- [ ] **Step 4: Commit**

```bash
git add .gitignore .env.example backend/requirements.txt backend/config/__init__.py backend/audio/__init__.py backend/tests/__init__.py data/.gitkeep README.md
git commit -m "chore: scaffold backend environment for audio capture"
```

---

### Task 2: Config loader

**Files:**
- Create: `backend/config/defaults.json`
- Create: `backend/config/schema.py`
- Create: `backend/config/loader.py`
- Test: `backend/tests/test_config_loader.py`

**Interfaces:**
- Consumes: defaults JSON + optional user JSON + `.env`
- Produces: `load_config(...) -> AppConfig`, `merge_user_config(current, patch) -> AppConfig`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_config_loader.py`:

```python
import json
from pathlib import Path

import pytest

from backend.config.loader import load_config, merge_user_config


def test_load_defaults(tmp_path: Path):
    defaults = Path("backend/config/defaults.json")
    cfg = load_config(defaults, tmp_path / "missing.json", None)
    assert cfg.audio.sample_rate == 16000
    assert cfg.audio.chunk_ms == 30
    assert cfg.server.host == "127.0.0.1"
    assert cfg.server.port == 8765
    assert cfg.llm.model == "claude-sonnet-4-6"
    assert cfg.stt.engine == "local"
    assert cfg.stt.local_model_size == "small"
    assert cfg.anthropic_api_key is None


def test_user_overlay_and_env(tmp_path: Path, monkeypatch):
    defaults = Path("backend/config/defaults.json")
    user = tmp_path / "config.json"
    user.write_text(json.dumps({"llm": {"temperature": 0.9, "max_tokens": 9999}}))
    env = tmp_path / ".env"
    env.write_text("ANTHROPIC_API_KEY=sk-test\nLOG_LEVEL=debug\n")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    cfg = load_config(defaults, user, env)
    assert cfg.llm.temperature == 0.9
    assert cfg.llm.max_tokens == 1500  # clamped
    assert cfg.anthropic_api_key == "sk-test"
    assert cfg.log_level == "debug"


def test_reject_non_loopback_host(tmp_path: Path):
    defaults = Path("backend/config/defaults.json")
    user = tmp_path / "config.json"
    user.write_text(json.dumps({"server": {"host": "0.0.0.0"}}))
    with pytest.raises(ValueError, match="CONFIG_INVALID"):
        load_config(defaults, user, None)


def test_cloud_stt_falls_back_without_key(tmp_path: Path):
    defaults = Path("backend/config/defaults.json")
    user = tmp_path / "config.json"
    user.write_text(json.dumps({"stt": {"engine": "cloud", "cloud_provider": "deepgram"}}))
    cfg = load_config(defaults, user, None)
    assert cfg.stt.engine == "local"


def test_merge_user_config_llm_style():
    defaults = Path("backend/config/defaults.json")
    cfg = load_config(defaults, Path("nope.json"), None)
    merged = merge_user_config(cfg, {"llm": {"answer_style": "star_format"}})
    assert merged.llm.answer_style == "star_format"
    assert merged.llm.model == cfg.llm.model
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest backend/tests/test_config_loader.py -v`

Expected: FAIL with import error for `backend.config.loader`.

- [ ] **Step 3: Write defaults.json**

Copy the JSON object from [specs/04-configuration.md](../specs/04-configuration.md) §2 into `backend/config/defaults.json` unchanged (including `server`).

- [ ] **Step 4: Write schema.py and loader.py**

`backend/config/schema.py` must define every frozen dataclass exactly as in [specs/03-module-specifications.md](../specs/03-module-specifications.md) §1: `LlmConfig`, `SttConfig`, `QuestionDetectionConfig`, `ContextConfig`, `AudioConfig`, `OverlayConfig`, `StorageConfig`, `ServerConfig`, `AppConfig`.

`backend/config/loader.py` must implement:

```python
def load_config(defaults_path: Path, user_config_path: Path, env_path: Path | None) -> AppConfig: ...
def merge_user_config(current: AppConfig, patch: dict) -> AppConfig: ...
```

Rules (implement all):
- Deep-merge user JSON over defaults; unknown keys ignored
- Load dotenv from `env_path` if provided
- Clamp `llm.temperature` to `[0, 1]`, `llm.max_tokens` to `[50, 1500]`
- `stt.engine == "cloud"` without `DEEPGRAM_API_KEY` → engine `local`
- `server.host != "127.0.0.1"` → `raise ValueError("CONFIG_INVALID: server.host must be 127.0.0.1")`
- `answer_style` not in `{concise, detailed, star_format}` → default `concise`
- `anthropic_api_key` may be `None` (do not raise)

Use `sys.path` so tests import `backend.*` from repo root, or run pytest from repo root with `PYTHONPATH=.`. Add empty `backend/__init__.py`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest backend/tests/test_config_loader.py -v`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/config backend/__init__.py backend/tests/test_config_loader.py
git commit -m "feat: load and validate AppConfig from defaults, user json, and env"
```

---

### Task 3: AudioCapture with fake device (unit tests)

**Files:**
- Create: `backend/audio/capture.py`
- Create: `backend/audio/devices.py`
- Test: `backend/tests/test_audio_capture.py`

**Interfaces:**
- Consumes: `AudioConfig`
- Produces: `AudioChunk`, `AudioCapture.start/stop/is_running`, `AudioCaptureError(code="AUDIO_DEVICE_NOT_FOUND")`, `list_loopback_devices()`

- [ ] **Step 1: Write the failing tests**

```python
import asyncio
import time

import pytest

from backend.audio.capture import AudioCapture, AudioCaptureError, AudioChunk
from backend.config.schema import AudioConfig


def _cfg(device="fake"):
    return AudioConfig(input_device=device, sample_rate=16000, chunk_ms=30)


@pytest.mark.asyncio
async def test_fake_capture_emits_pcm_chunks():
    cap = AudioCapture(_cfg("fake"), source="fake")
    q: asyncio.Queue[AudioChunk] = asyncio.Queue()
    cap.start(q)
    chunk = await asyncio.wait_for(q.get(), timeout=1)
    cap.stop()
    assert isinstance(chunk, AudioChunk)
    assert chunk.sample_rate == 16000
    assert len(chunk.pcm) == 16000 * 30 // 1000 * 2  # s16le mono
    assert chunk.timestamp_ms <= int(time.time() * 1000)


def test_missing_device_raises():
    cap = AudioCapture(_cfg("does-not-exist"), source="fake")
    with pytest.raises(AudioCaptureError) as ei:
        cap.start(asyncio.Queue())
    assert ei.value.code == "AUDIO_DEVICE_NOT_FOUND"
    assert cap.is_running() is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_audio_capture.py -v`

Expected: FAIL import `AudioCapture`.

- [ ] **Step 3: Write minimal implementation**

In `backend/audio/capture.py`:

- `AudioChunk(pcm: bytes, sample_rate: int, timestamp_ms: int)` frozen dataclass
- `AudioCaptureError` with `.code` and `.message`
- `AudioCapture.__init__(self, config: AudioConfig, source: str = "loopback")`
- If `source == "fake"` and `input_device == "fake"`: a daemon thread/async task puts silence chunks (`b"\x00" * frames * 2`) every `chunk_ms`
- If `source == "fake"` and device is anything else: `start` raises `AudioCaptureError("AUDIO_DEVICE_NOT_FOUND", ...)`
- `source == "loopback"`: not fully wired yet; `start` may raise `NotImplementedError` until Task 4
- `stop` sets `is_running` false and joins the worker

`backend/audio/devices.py`:

```python
def list_loopback_devices() -> list[dict]:
    return [{"id": "system_default_loopback", "name": "Default loopback", "is_loopback": True}]
```

Real enumeration comes in Task 4.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest backend/tests/test_audio_capture.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/audio/capture.py backend/audio/devices.py backend/tests/test_audio_capture.py
git commit -m "feat: add AudioCapture queue interface with fake source"
```

---

### Task 4: Platform loopback + WAV dump CLI

**Files:**
- Modify: `backend/audio/capture.py`
- Modify: `backend/audio/devices.py`
- Create: `backend/audio/wav_dump.py`

**Interfaces:**
- Consumes: `AudioCapture(source="loopback")`
- Produces: WAV file from real system audio; `list_loopback_devices()` returns OS devices

- [ ] **Step 1: Write WAV dump CLI**

`backend/audio/wav_dump.py`:

```python
import argparse
import asyncio
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf

# ensure repo root on path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.audio.capture import AudioCapture, AudioCaptureError
from backend.config.loader import load_config


async def dump(seconds: float, out: Path) -> None:
    cfg = load_config(Path("backend/config/defaults.json"), Path("data/config.json"), Path(".env"))
    cap = AudioCapture(cfg.audio, source="loopback")
    q = asyncio.Queue()
    cap.start(q)
    frames = []
    deadline = time.time() + seconds
    try:
        while time.time() < deadline:
            chunk = await asyncio.wait_for(q.get(), timeout=1)
            frames.append(np.frombuffer(chunk.pcm, dtype=np.int16))
    finally:
        cap.stop()
    pcm = np.concatenate(frames) if frames else np.zeros(0, dtype=np.int16)
    out.parent.mkdir(parents=True, exist_ok=True)
    sf.write(out, pcm, cfg.audio.sample_rate, subtype="PCM_16")
    print(f"wrote {out} samples={len(pcm)}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--seconds", type=float, default=5)
    p.add_argument("--out", default="data/loopback.wav")
    args = p.parse_args()
    try:
        asyncio.run(dump(args.seconds, Path(args.out)))
    except AudioCaptureError as e:
        print(f"{e.code}: {e.message}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Implement Windows WASAPI loopback in `capture.py`**

When `source == "loopback"` and `sys.platform == "win32"`:
- Use `pyaudiowpatch` (`pyaudio`) WASAPI loopback
- If `input_device == "system_default_loopback"`, select the default output’s loopback device
- Stream callback converts to int16 mono 16 kHz (resample if the device rate differs; if resampling is large, use `numpy` linear resample)
- Enqueue `AudioChunk` with `timestamp_ms = int(time.time() * 1000)`
- If no loopback device: raise `AudioCaptureError("AUDIO_DEVICE_NOT_FOUND", "Could not initialize audio loopback device.")`

When `sys.platform != "win32"`:
- Use `sounddevice` InputStream on a device whose name/id matches `input_device`, or the first device with `is_loopback` from `list_loopback_devices()`
- Same PCM format and error code

`devices.py` `list_loopback_devices()`:
- Windows: enumerate WASAPI loopback devices; always include `{id: "system_default_loopback", name: "Default loopback", is_loopback: True}` first
- Others: enumerate `sounddevice.query_devices()`, mark monitor/loopback-like names (`BlackHole`, `Loopback`, `monitor`)

- [ ] **Step 3: Manual verification**

Play music or a YouTube video. Run:

```
python backend/audio/wav_dump.py --seconds 5 --out data/loopback.wav
```

Expected: `data/loopback.wav` plays back **system audio**, not (only) the mic.

If it fails with `AUDIO_DEVICE_NOT_FOUND`, fix device selection before leaving this phase.

- [ ] **Step 4: Re-run unit tests**

Run: `python -m pytest backend/tests/test_config_loader.py backend/tests/test_audio_capture.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/audio
git commit -m "feat: capture system loopback audio and dump to wav"
```

---

## Phase 1 acceptance

- [ ] `python -m pytest backend/tests/test_config_loader.py backend/tests/test_audio_capture.py` passes
- [ ] WAV dump records system audio on the target OS
- [ ] Missing fake device still raises `AUDIO_DEVICE_NOT_FOUND`

**Stop here. Do not implement STT.**
