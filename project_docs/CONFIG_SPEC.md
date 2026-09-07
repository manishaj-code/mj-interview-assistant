# Configuration Specification — AI Interview Assistant

Defines every configurable value the app needs, where it lives, and its default. Backend reads from environment variables (`.env`) for secrets and a `config.json` (editable via the Settings UI) for user preferences.

---

## 1. Environment Variables (`.env`, not committed to git)

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | Claude API key used for answer generation |
| `DEEPGRAM_API_KEY` | No | Only required if cloud STT is enabled instead of local Whisper |
| `LOG_LEVEL` | No | `debug` \| `info` \| `warn` \| `error` — default `info` |

`.env.example` should be committed with placeholder values so Claude Code scaffolds the loading logic correctly.

---

## 2. User Config (`config.json`, local, editable via Settings UI)

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
  }
}
```

### Field notes

- **`llm.answer_style`**: `"concise"` \| `"detailed"` \| `"star_format"` — controls the system prompt template used by the LLM client.
- **`stt.engine`**: `"local"` \| `"cloud"` — if `"cloud"`, `cloud_provider` must be set (e.g. `"deepgram"`) and the matching API key must exist in `.env`.
- **`question_detection.silence_gap_ms`**: tunable during testing; start at 800ms, adjust based on false positive/negative rate.
- **`overlay.content_protection`**: maps directly to Electron's `setContentProtection()`. Should default to `true`; expose as a toggle in case it causes rendering issues on some GPUs (a known Electron quirk on certain Windows configs).
- **`storage.session_history_enabled`**: if `false`, no Q&A data is written to disk — for privacy-conscious runs.

---

## 3. Config Loading Order

1. Load `config.json` defaults (bundled with app).
2. Overlay any values from a user-edited `config.json` in the app's userData directory.
3. Load secrets from `.env` (never stored in `config.json`).
4. Settings UI writes changes back to the userData `config.json` only — never touches `.env`.

---

## 4. Validation Rules (for Claude Code to implement)

- Reject startup if `ANTHROPIC_API_KEY` is missing — show a setup screen instead of crashing.
- If `stt.engine == "cloud"` but no matching API key is present, fall back to `"local"` and surface a warning in the UI.
- Clamp `llm.temperature` to `[0, 1]` and `llm.max_tokens` to a sane range (e.g. `50–1500`) to avoid runaway costs.
