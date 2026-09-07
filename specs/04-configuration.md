# Configuration Specification — AI Interview Assistant

Backend reads secrets from environment (`.env`) and user preferences from `config.json`. Settings UI never writes secrets.

## 1. Environment variables (`.env`, gitignored)

| Variable | Required | Default | Description |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | Yes for Live | none | Claude API key |
| `DEEPGRAM_API_KEY` | Only if cloud STT | none | Deepgram key |
| `LOG_LEVEL` | No | `info` | `debug` \| `info` \| `warn` \| `error` |

Commit `.env.example` with empty placeholders:

```
ANTHROPIC_API_KEY=
DEEPGRAM_API_KEY=
LOG_LEVEL=info
```

## 2. User config (`config.json`)

Bundled defaults live at `backend/config/defaults.json`. User overlay file lives in Electron `app.getPath('userData')/config.json`. During backend-only phases (before Electron), user file is `./data/config.json`.

```json
{
  "llm": {
    "model": "claude-sonnet-4-6",
    "max_tokens": 500,
    "temperature": 0.4,
    "answer_style": "concise"
  },
  "stt": {
    "engine": "local",
    "local_model_size": "small",
    "cloud_provider": null
  },
  "question_detection": {
    "silence_gap_ms": 800,
    "use_llm_fallback_classifier": true
  },
  "context": {
    "max_history_pairs": 5,
    "resume_path": null,
    "job_description": ""
  },
  "audio": {
    "input_device": "system_default_loopback",
    "sample_rate": 16000,
    "chunk_ms": 30
  },
  "overlay": {
    "always_on_top": true,
    "content_protection": true,
    "opacity": 0.92,
    "hotkey_toggle_visibility": "CommandOrControl+Shift+H",
    "hotkey_panic_hide": "CommandOrControl+Shift+Escape"
  },
  "storage": {
    "session_history_enabled": true,
    "session_history_path": "./data/sessions.sqlite"
  },
  "server": {
    "host": "127.0.0.1",
    "port": 8765
  }
}
```

### Field rules

| Field | Allowed values / range |
|---|---|
| `llm.answer_style` | `concise` \| `detailed` \| `star_format` |
| `llm.temperature` | clamped to `[0, 1]` |
| `llm.max_tokens` | clamped to `[50, 1500]` |
| `stt.engine` | `local` \| `cloud` |
| `stt.local_model_size` | `tiny` \| `base` \| `small` \| `medium` \| `large-v3` |
| `stt.cloud_provider` | `null` or `deepgram` when engine is `cloud` |
| `question_detection.silence_gap_ms` | integer `200`–`3000` |
| `context.max_history_pairs` | integer `0`–`20` |
| `audio.sample_rate` | `16000` only in MVP |
| `audio.chunk_ms` | `20`, `30`, or `40` |
| `overlay.opacity` | `0.4`–`1.0` |
| `server.host` | must be `127.0.0.1` |
| `server.port` | `1024`–`65535`, default `8765` |

## 3. Load order

1. Load `backend/config/defaults.json`.
2. Deep-merge user `config.json` if the file exists.
3. Load `.env` (and process environment). Env wins for secrets and `LOG_LEVEL` only.
4. Validate. Apply fallbacks listed below.
5. Settings UI writes **only** the user `config.json`. It never writes `.env`.

## 4. Validation and fallbacks

- Missing `ANTHROPIC_API_KEY`: config loads, but Live is blocked. Surface Setup. Do not crash the process.
- `stt.engine == "cloud"` and `DEEPGRAM_API_KEY` missing: set engine to `local`, keep a warning flag `stt_cloud_fallback: true` for the UI (include in first `status` payload after connect as `warnings: ["STT_CLOUD_FALLBACK"]`).
- `server.host` other than `127.0.0.1`: reject with `CONFIG_INVALID`.
- Unknown keys in user JSON: ignore (forward compatible).
- Invalid enum: replace with default and include a warning string.

## 5. Runtime updates

`update_config` from the frontend is a **shallow-per-section deep merge** of the payload onto current user config, then re-validate, then persist user `config.json`.

Changes that require restart of listening (apply on next `start_listening` if currently listening, after a stop/start performed by backend):

- `stt.*`
- `audio.*`
- `server.*` (port change requires process restart; emit `error` `CONFIG_INVALID` with message that port changes need app restart, and do not apply port live)

Changes applied immediately:

- `llm.*` (including `answer_style`)
- `question_detection.*`
- `context.max_history_pairs`
- `overlay.*` (Electron reads overlay fields; backend may ignore them except when forwarding config)
- `storage.session_history_enabled`
