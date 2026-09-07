from __future__ import annotations

import json
import os
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from backend.config.schema import (
    AppConfig,
    AudioConfig,
    ContextConfig,
    LlmConfig,
    OverlayConfig,
    QuestionDetectionConfig,
    ServerConfig,
    StorageConfig,
    SttConfig,
)

_KNOWN_SECTIONS = (
    "llm",
    "stt",
    "question_detection",
    "context",
    "audio",
    "overlay",
    "storage",
    "server",
)
_ANSWER_STYLES = {"concise", "detailed", "star_format"}
_STT_ENGINES = {"local", "cloud"}
_MODEL_SIZES = {"tiny", "base", "small", "medium", "large-v3"}
_LOG_LEVELS = {"debug", "info", "warn", "error"}
_CHUNK_MS = {20, 30, 40}


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in overlay.items():
        if key not in merged:
            continue
        if isinstance(merged[key], dict) and isinstance(value, dict):
            for inner_key, inner_val in value.items():
                if inner_key in merged[key]:
                    merged[key][inner_key] = inner_val
        else:
            merged[key] = value
    return merged


def _clamp(value: float | int, low: float | int, high: float | int):
    return max(low, min(high, value))


def _build_config(
    data: dict[str, Any],
    anthropic_api_key: str | None,
    groq_api_key: str | None,
    gemini_api_key: str | None,
    deepgram_api_key: str | None,
    log_level: str,
) -> AppConfig:
    llm = data["llm"]
    stt = data["stt"]
    qd = data["question_detection"]
    ctx = data["context"]
    audio = data["audio"]
    overlay = data["overlay"]
    storage = data["storage"]
    server = data["server"]

    answer_style = llm.get("answer_style", "concise")
    if answer_style not in _ANSWER_STYLES:
        answer_style = "concise"

    engine = stt.get("engine", "local")
    if engine not in _STT_ENGINES:
        engine = "local"
    if engine == "cloud" and not deepgram_api_key:
        engine = "local"

    model_size = stt.get("local_model_size", "small")
    if model_size not in _MODEL_SIZES:
        model_size = "small"

    cloud_provider = stt.get("cloud_provider")
    if cloud_provider not in (None, "deepgram"):
        cloud_provider = None

    host = server.get("host", "127.0.0.1")
    if host != "127.0.0.1":
        raise ValueError("CONFIG_INVALID: server.host must be 127.0.0.1")

    chunk_ms = audio.get("chunk_ms", 30)
    if chunk_ms not in _CHUNK_MS:
        chunk_ms = 30

    if log_level not in _LOG_LEVELS:
        log_level = "info"

    return AppConfig(
        llm=LlmConfig(
            model=str(llm.get("model", "claude-sonnet-4-6")),
            max_tokens=int(_clamp(int(llm.get("max_tokens", 500)), 50, 1500)),
            temperature=float(_clamp(float(llm.get("temperature", 0.4)), 0, 1)),
            answer_style=answer_style,
        ),
        stt=SttConfig(
            engine=engine,
            local_model_size=model_size,
            cloud_provider=cloud_provider,
        ),
        question_detection=QuestionDetectionConfig(
            silence_gap_ms=int(_clamp(int(qd.get("silence_gap_ms", 800)), 200, 3000)),
            use_llm_fallback_classifier=bool(qd.get("use_llm_fallback_classifier", True)),
        ),
        context=ContextConfig(
            max_history_pairs=int(_clamp(int(ctx.get("max_history_pairs", 5)), 0, 20)),
            resume_path=ctx.get("resume_path"),
            job_description=str(ctx.get("job_description", "")),
        ),
        audio=AudioConfig(
            input_device=str(audio.get("input_device", "system_default_loopback")),
            sample_rate=16000,
            chunk_ms=int(chunk_ms),
        ),
        overlay=OverlayConfig(
            always_on_top=bool(overlay.get("always_on_top", True)),
            content_protection=bool(overlay.get("content_protection", True)),
            opacity=float(_clamp(float(overlay.get("opacity", 0.92)), 0.4, 1.0)),
            hotkey_toggle_visibility=str(
                overlay.get("hotkey_toggle_visibility", "CommandOrControl+Shift+H")
            ),
            hotkey_panic_hide=str(
                overlay.get("hotkey_panic_hide", "CommandOrControl+Shift+Escape")
            ),
        ),
        storage=StorageConfig(
            session_history_enabled=bool(storage.get("session_history_enabled", True)),
            session_history_path=str(storage.get("session_history_path", "./data/sessions.sqlite")),
        ),
        server=ServerConfig(
            host="127.0.0.1",
            port=int(_clamp(int(server.get("port", 8765)), 1024, 65535)),
        ),
        anthropic_api_key=anthropic_api_key or None,
        groq_api_key=groq_api_key or None,
        gemini_api_key=gemini_api_key or None,
        deepgram_api_key=deepgram_api_key or None,
        log_level=log_level,
    )


def load_config(
    defaults_path: Path,
    user_config_path: Path,
    env_path: Path | None,
) -> AppConfig:
    with defaults_path.open(encoding="utf-8") as fh:
        data = json.load(fh)

    if user_config_path.exists():
        with user_config_path.open(encoding="utf-8") as fh:
            user = json.load(fh)
        if isinstance(user, dict):
            data = _deep_merge(data, {k: v for k, v in user.items() if k in _KNOWN_SECTIONS})

    if env_path is not None and env_path.exists():
        load_dotenv(env_path, override=False)

    anthropic = os.environ.get("ANTHROPIC_API_KEY") or None
    groq = os.environ.get("GROQ_API_KEY") or None
    gemini = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or None
    deepgram = os.environ.get("DEEPGRAM_API_KEY") or None
    log_level = os.environ.get("LOG_LEVEL", "info")
    return _build_config(data, anthropic, groq, gemini, deepgram, log_level)


def merge_user_config(current: AppConfig, patch: dict) -> AppConfig:
    data = asdict(current)
    secrets = {
        "anthropic_api_key": current.anthropic_api_key,
        "groq_api_key": current.groq_api_key,
        "gemini_api_key": current.gemini_api_key,
        "deepgram_api_key": current.deepgram_api_key,
        "log_level": current.log_level,
    }
    for key in secrets:
        data.pop(key, None)
    if isinstance(patch, dict):
        data = _deep_merge(data, {k: v for k, v in patch.items() if k in _KNOWN_SECTIONS})
    return _build_config(
        data,
        secrets["anthropic_api_key"],
        secrets["groq_api_key"],
        secrets["gemini_api_key"],
        secrets["deepgram_api_key"],
        secrets["log_level"],
    )
