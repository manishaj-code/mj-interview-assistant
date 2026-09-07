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
    assert cfg.groq_api_key is None
    assert cfg.gemini_api_key is None


def test_user_overlay_and_env(tmp_path: Path, monkeypatch):
    defaults = Path("backend/config/defaults.json")
    user = tmp_path / "config.json"
    user.write_text(json.dumps({"llm": {"temperature": 0.9, "max_tokens": 9999}}))
    env = tmp_path / ".env"
    env.write_text("GROQ_API_KEY=gsk-test\nGEMINI_API_KEY=gem-test\nLOG_LEVEL=debug\n")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    cfg = load_config(defaults, user, env)
    assert cfg.llm.temperature == 0.9
    assert cfg.llm.max_tokens == 1500  # clamped
    assert cfg.groq_api_key == "gsk-test"
    assert cfg.gemini_api_key == "gem-test"
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
