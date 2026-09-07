# WebSocket Event Contract — AI Interview Assistant

**URL:** `ws://127.0.0.1:8765` (port from `server.port`)  
**Format:** UTF-8 JSON. Every message has top-level `"type": string`.  
**Schema:** v1, additive only. Do not rename or remove fields.

Commands without a payload omit `payload`. Events always include `payload`.

`timestamp` / `timestamp_ms` values are Unix epoch milliseconds from the backend.

---

## 1. Frontend → Backend (commands)

### `start_listening`

```json
{ "type": "start_listening" }
```

Starts capture + STT + detection. If already listening, backend emits `status` `{ "state": "listening" }` and does nothing else.

### `stop_listening`

```json
{ "type": "stop_listening" }
```

Stops capture and in-flight LLM. State becomes `idle`.

### `update_context`

```json
{
  "type": "update_context",
  "payload": {
    "resume_text": "string",
    "job_description": "string"
  }
}
```

Both fields required (use `""` if empty). Replaces stored resume and JD. Does not start listening.

If `resume_text` is `""` and the context already has resume text, keep the existing resume and update JD only. Sending `resume_text: ""` when no resume is stored leaves resume empty.

### `update_config`

```json
{
  "type": "update_config",
  "payload": {
    "llm": { "answer_style": "detailed" }
  }
}
```

Partial document. Only provided sections are merged. See [04-configuration.md](04-configuration.md) for apply-now vs restart rules.

### `manual_answer_request`

```json
{ "type": "manual_answer_request" }
```

Treats `QuestionDetector.current_buffer_text()` as the question. Empty buffer → `error` `NO_TRANSCRIPT_BUFFER`.

### `extract_resume`

```json
{
  "type": "extract_resume",
  "payload": { "path": "C:/Users/me/resume.pdf" }
}
```

`path` must be a local filesystem path from Electron’s Open dialog. Backend extracts text, stores resume, and emits `context_updated`. Failure → `error` `RESUME_PARSE_FAILED`.

### `list_history`

```json
{ "type": "list_history" }
```

### `list_audio_devices`

```json
{ "type": "list_audio_devices" }
```

---

## 2. Backend → Frontend (events)

### `status`

```json
{
  "type": "status",
  "payload": {
    "state": "listening",
    "warnings": [],
    "missing_api_key": false
  }
}
```

`state`: `idle` \| `listening` \| `error`  
`warnings`: optional array of strings, e.g. `["STT_CLOUD_FALLBACK"]`.  
`missing_api_key`: `true` when `ANTHROPIC_API_KEY` is unset. Setup uses this to block Start.

Emit on connect, after `start_listening`, after `stop_listening`, and when entering `error`.

### `transcript_partial`

```json
{
  "type": "transcript_partial",
  "payload": {
    "text": "so can you tell me about a time",
    "timestamp": 1730000000000
  }
}
```

### `transcript_final`

```json
{
  "type": "transcript_final",
  "payload": {
    "text": "So can you tell me about a time you handled conflict?",
    "timestamp": 1730000000000
  }
}
```

### `question_detected`

```json
{
  "type": "question_detected",
  "payload": {
    "question_text": "Can you tell me about a time you handled conflict?",
    "timestamp": 1730000000000
  }
}
```

### `answer_token`

```json
{
  "type": "answer_token",
  "payload": {
    "token": "In my",
    "seq": 1
  }
}
```

`seq` starts at `1` for each answer and increases by 1. Frontend appends in `seq` order. If `seq` is missing a number, wait up to 100 ms then append anyway to avoid stalling.

### `answer_complete`

```json
{
  "type": "answer_complete",
  "payload": {
    "question_text": "Can you tell me about a time you handled conflict?",
    "full_answer": "In my previous role...",
    "duration_ms": 2100
  }
}
```

`duration_ms` is question-detect time to last token.

### `error`

```json
{
  "type": "error",
  "payload": {
    "code": "STT_INIT_FAILED",
    "message": "Could not initialize audio loopback device.",
    "fatal": false
  }
}
```

Codes: see [03-module-specifications.md](03-module-specifications.md) §11.

### `context_updated`

```json
{
  "type": "context_updated",
  "payload": {
    "resume_chars": 4200,
    "job_description_chars": 800,
    "resume_preview": "first 200 chars..."
  }
}
```

Emitted after successful `update_context` or `extract_resume`.

### `history_data`

```json
{
  "type": "history_data",
  "payload": {
    "sessions": [
      {
        "id": 1,
        "started_at_ms": 1730000000000,
        "entries": [
          {
            "id": 1,
            "question_text": "...",
            "full_answer": "...",
            "timestamp_ms": 1730000000100,
            "duration_ms": 2100
          }
        ]
      }
    ]
  }
}
```

If history is disabled, `sessions` is `[]`.

### `audio_devices`

```json
{
  "type": "audio_devices",
  "payload": {
    "devices": [
      { "id": "system_default_loopback", "name": "Default loopback", "is_loopback": true }
    ]
  }
}
```

---

## 3. Sequence (happy path)

```
FE → BE   start_listening
BE → FE   status { state: "listening" }
BE → FE   transcript_partial (N times)
BE → FE   transcript_final
BE → FE   question_detected
BE → FE   answer_token (N times, seq 1..N)
BE → FE   answer_complete
```

## 4. Connection rules

- Backend accepts multiple connections and broadcasts every event to all clients. MVP expects one Electron client.
- If the sidecar restarts, Electron reconnects every 500 ms, then 1 s, 2 s, cap 5 s, indefinitely while the app is open.
- On each new socket, backend sends `status` with current state.
- Heartbeat: not required in v1. TCP close is the disconnect signal.

## 5. Implementation constraints

- One asyncio loop for WS + pipeline. Whisper in a thread pool.
- Do not bind `0.0.0.0`.
- Ignore unknown JSON keys on receive (additive).
- Invalid JSON: close is not required; emit `error` `UNKNOWN_COMMAND` with message `invalid json`.
