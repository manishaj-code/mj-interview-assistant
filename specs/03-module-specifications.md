# Module Specifications — AI Interview Assistant

All Python public types below are the names later phases must use. Do not rename them in implementation.

Shared timestamp rule: `timestamp_ms` is Unix epoch milliseconds, produced by the backend.

---

## 1. Config loader

**Files:** `backend/config/loader.py`, `backend/config/schema.py`, `backend/config/defaults.json`

**Does:** load defaults → user `config.json` → `.env` secrets. Validate. Expose a frozen `AppConfig`.

**Produces:**

```python
@dataclass(frozen=True)
class LlmConfig:
    model: str
    max_tokens: int
    temperature: float
    answer_style: str  # "concise" | "detailed" | "star_format"

@dataclass(frozen=True)
class SttConfig:
    engine: str  # "local" | "cloud"
    local_model_size: str  # "tiny" | "base" | "small" | "medium" | "large-v3"
    cloud_provider: str | None  # "deepgram" | None

@dataclass(frozen=True)
class QuestionDetectionConfig:
    silence_gap_ms: int
    use_llm_fallback_classifier: bool

@dataclass(frozen=True)
class ContextConfig:
    max_history_pairs: int
    resume_path: str | None
    job_description: str

@dataclass(frozen=True)
class AudioConfig:
    input_device: str
    sample_rate: int
    chunk_ms: int

@dataclass(frozen=True)
class OverlayConfig:
    always_on_top: bool
    content_protection: bool
    opacity: float
    hotkey_toggle_visibility: str
    hotkey_panic_hide: str

@dataclass(frozen=True)
class StorageConfig:
    session_history_enabled: bool
    session_history_path: str

@dataclass(frozen=True)
class ServerConfig:
    host: str  # always "127.0.0.1" for MVP
    port: int  # default 8765

@dataclass(frozen=True)
class AppConfig:
    llm: LlmConfig
    stt: SttConfig
    question_detection: QuestionDetectionConfig
    context: ContextConfig
    audio: AudioConfig
    overlay: OverlayConfig
    storage: StorageConfig
    server: ServerConfig
    anthropic_api_key: str | None
    deepgram_api_key: str | None
    log_level: str
```

```python
def load_config(
    defaults_path: Path,
    user_config_path: Path,
    env_path: Path | None,
) -> AppConfig: ...

def merge_user_config(current: AppConfig, patch: dict) -> AppConfig: ...
```

Validation rules: [04-configuration.md](04-configuration.md).

---

## 2. Audio capture

**Files:** `backend/audio/capture.py`, `backend/audio/devices.py`

**Does:** capture **system loopback** (interviewer / speaker output), not the default microphone.

**Produces:**

```python
@dataclass(frozen=True)
class AudioChunk:
    pcm: bytes          # s16le, mono
    sample_rate: int    # 16000
    timestamp_ms: int

class AudioCaptureError(Exception):
    def __init__(self, code: str, message: str): ...
    # code: AUDIO_DEVICE_NOT_FOUND

class AudioCapture:
    def __init__(self, config: AudioConfig): ...
    def start(self, queue: asyncio.Queue[AudioChunk]) -> None: ...
    def stop(self) -> None: ...
    def is_running(self) -> bool: ...
```

```python
def list_loopback_devices() -> list[dict]:  # [{id, name, is_loopback}]
```

PCM format is always 16-bit signed little-endian, mono, `config.audio.sample_rate`. Chunk size in frames = `sample_rate * chunk_ms / 1000`.

Windows: WASAPI loopback via `pyaudiowpatch`.  
macOS/Linux: `sounddevice` on the configured loopback/monitor device.  
`input_device == "system_default_loopback"` selects the platform default loopback; if none exists, raise `AUDIO_DEVICE_NOT_FOUND`.

---

## 3. STT

**Files:** `backend/stt/transcriber.py`

**Does:** turn PCM chunks into partial and final transcript events.

```python
@dataclass(frozen=True)
class TranscriptEvent:
    text: str
    is_final: bool
    timestamp_ms: int

class Transcriber:
    def __init__(self, config: SttConfig): ...
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def process_chunk(self, chunk: AudioChunk) -> TranscriptEvent | None: ...
```

- `engine == "local"`: `faster-whisper`, model `local_model_size`, compute type `int8` on CPU. Inference in a thread pool.
- `engine == "cloud"` and provider `deepgram`: streaming Deepgram. If key missing at load time, loader already fell back to local; transcriber must not assume cloud.
- Partial events may be emitted often. Final events must be stable text for detection.
- Empty/whitespace-only text is not emitted.

---

## 4. Question detection

**Files:** `backend/detection/question_detector.py`

**Does:** decide when transcript text is a complete question worth answering.

Layered, cheapest first:

1. **Silence gap:** after speech, gap ≥ `silence_gap_ms` (from VAD and/or time since last non-empty transcript).
2. **Lexical/punctuation:** text ends with `?` **or** starts (case-insensitive) with one of: `what`, `why`, `how`, `when`, `where`, `who`, `which`, `can you`, `could you`, `would you`, `tell me`, `describe`, `explain`, `walk me through`, `have you`, `do you`, `did you`, `are you`.
3. **LLM fallback:** only if `use_llm_fallback_classifier` is true **and** layers 1–2 disagree (silence gap fired but lexical check failed). Cheap classifier prompt; boolean only. Uses Anthropic with `max_tokens=20`. If the classifier call fails, treat as **not** a question (do not block the pipeline).

```python
@dataclass(frozen=True)
class DetectedQuestion:
    question_text: str
    timestamp_ms: int

class QuestionDetector:
    def __init__(self, config: QuestionDetectionConfig, classify_fn=None): ...
    def on_transcript(self, event: TranscriptEvent) -> DetectedQuestion | None: ...
    def on_silence(self, now_ms: int) -> DetectedQuestion | None: ...
    def current_buffer_text(self) -> str: ...
    def reset(self) -> None: ...
```

- Detection runs on **final** transcripts plus silence. Partials update an internal display buffer only.
- The pipeline must call `on_silence(now_ms)` at least every 50 ms while listening so the silence-gap heuristic can fire without an empty STT event.
- Duplicate questions (same normalized text within 5 seconds) are ignored.
- `manual_answer_request` uses `current_buffer_text()`; if buffer is empty, backend emits `error` `NO_TRANSCRIPT_BUFFER` (`fatal: false`).

---

## 5. Context manager

**Files:** `backend/context/context_manager.py`, `backend/context/pdf_extract.py`

```python
def extract_resume_text(file_path: Path) -> str: ...
# PDF via pypdf. .txt/.md read as UTF-8. Other extensions: raise ValueError.

class ContextManager:
    def __init__(self, config: ContextConfig, answer_style: str): ...
    def set_resume(self, text: str) -> None: ...
    def set_job_description(self, text: str) -> None: ...
    def set_answer_style(self, style: str) -> None: ...
    def add_qa_pair(self, question: str, answer: str) -> None: ...
    def build_messages(self, question: str) -> list[dict]: ...
```

`build_messages` returns Anthropic-style:

```python
[
  {"role": "user", "content": "<assembled prompt>"},
]
```

System instructions are passed separately to the LLM client as `system=` (not as a messages role, matching Anthropic Messages API).

System prompt rules by `answer_style`:

- `concise`: 4–8 spoken sentences, first person, no markdown headings, no bullet walls unless listing 2–4 short points.
- `detailed`: up to ~12 sentences, still spoken-aloud first person.
- `star_format`: Situation, Task, Action, Result as four short spoken paragraphs. No “STAR:” labels if they would sound unnatural; use natural transitions.

Always include: resume text (or “(none provided)”), JD (or “(none provided)”), last N Q&A pairs newest-last.

---

## 6. LLM client

**Files:** `backend/llm/claude_client.py`

```python
class LlmError(Exception):
    def __init__(self, code: str, message: str): ...
    # LLM_API_ERROR | LLM_TIMEOUT

class ClaudeClient:
    def __init__(self, config: LlmConfig, api_key: str): ...
    async def stream_answer(
        self,
        system: str,
        messages: list[dict],
        timeout_s: float = 30.0,
    ) -> AsyncIterator[str]: ...
    async def classify_is_question(self, text: str) -> bool: ...
    def cancel_current(self) -> None: ...
```

- Streaming uses Anthropic Messages `stream=True` (or SDK async stream).
- Yield **text deltas only** (not full snapshots).
- Timeout `30s` to first token: raise `LLM_TIMEOUT`.
- After start, overall generation timeout `90s`: raise `LLM_TIMEOUT`.
- `classify_is_question` is a non-streaming, max 20-token call.

---

## 7. WebSocket server

**Files:** `backend/server/ws_server.py`, `backend/server/events.py`

Bind `127.0.0.1` only. Schema: [05-websocket-contract.md](05-websocket-contract.md).

```python
def make_event(type: str, payload: dict | None = None) -> str: ...
def parse_command(raw: str) -> dict: ...  # raises ValueError

class WsServer:
    def __init__(self, host: str, port: int, pipeline: Pipeline): ...
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def broadcast(self, message: dict) -> None: ...
```

Unknown `type` from frontend: ignore, emit `error` `UNKNOWN_COMMAND`, `fatal: false`.

---

## 8. Pipeline

**File:** `backend/pipeline.py`

Wires capture → STT → detector → context → LLM → broadcast → optional session store.

```python
class Pipeline:
    def __init__(self, config: AppConfig, broadcast, store): ...
    async def start_listening(self) -> None: ...
    async def stop_listening(self) -> None: ...
    async def update_context(self, resume_text: str, job_description: str) -> None: ...
    async def extract_resume(self, path: str) -> None: ...
    async def update_config(self, patch: dict) -> AppConfig: ...
    async def manual_answer_request(self) -> None: ...
    async def list_history(self) -> dict: ...
    def list_audio_devices(self) -> list[dict]: ...
    def state(self) -> str:  # idle | listening | error
```

---

## 9. Session store

**File:** `backend/storage/session_store.py`

```python
@dataclass(frozen=True)
class HistoryEntry:
    id: int
    question_text: str
    full_answer: str
    timestamp_ms: int
    duration_ms: int

class SessionStore:
    def __init__(self, path: str, enabled: bool): ...
    def start_session(self) -> int: ...
    def append(self, question_text: str, full_answer: str, timestamp_ms: int, duration_ms: int) -> None: ...
    def list_sessions(self) -> list[dict]: ...
    def list_entries(self, session_id: int) -> list[HistoryEntry]: ...
    def close(self) -> None: ...
```

SQLite schema:

```sql
CREATE TABLE sessions (
  id INTEGER PRIMARY KEY,
  started_at_ms INTEGER NOT NULL
);
CREATE TABLE entries (
  id INTEGER PRIMARY KEY,
  session_id INTEGER NOT NULL,
  question_text TEXT NOT NULL,
  full_answer TEXT NOT NULL,
  timestamp_ms INTEGER NOT NULL,
  duration_ms INTEGER NOT NULL,
  FOREIGN KEY(session_id) REFERENCES sessions(id)
);
```

If `enabled` is false, all writes are no-ops; reads return empty lists.

---

## 10. Electron shell

**Files:** `electron/main.js`, `electron/preload.js`, `electron/renderer/*`

Responsibilities: windows, `setContentProtection`, `setAlwaysOnTop(..., 'screen-saver')`, global shortcuts, spawn sidecar, reconnect WS.

No business logic in the renderer beyond rendering events and sending commands. Preload exposes a narrow `window.api`.

---

## 11. Error codes

| Code | Meaning | Typical `fatal` |
|---|---|---|
| `AUDIO_DEVICE_NOT_FOUND` | No loopback device | false |
| `STT_INIT_FAILED` | Whisper/Deepgram failed to start | false |
| `LLM_API_ERROR` | Anthropic HTTP/API error | false |
| `LLM_TIMEOUT` | First-token or total timeout | false |
| `LLM_CANCELLED` | Stream aborted for a newer question | false |
| `CONFIG_INVALID` | Config failed validation | true if key missing at boot |
| `NO_TRANSCRIPT_BUFFER` | Manual answer with empty buffer | false |
| `UNKNOWN_COMMAND` | Bad WS type | false |
| `MISSING_API_KEY` | No `ANTHROPIC_API_KEY` | true until user adds it |
| `RESUME_PARSE_FAILED` | PDF/text resume could not be read | false |

`fatal: true` means the pipeline moves to `error` and stops listening. `fatal: false` is shown in the overlay; listening continues when possible.
