import asyncio
from pathlib import Path

import pytest

from backend.config.loader import load_config
from backend.pipeline import Pipeline


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


@pytest.mark.asyncio
async def test_extract_resume_and_jd_in_prompt(tmp_path):
    events = []

    async def broadcast(msg):
        events.append(msg)

    cfg = load_config(Path("backend/config/defaults.json"), tmp_path / "no.json", None)
    p = Pipeline(cfg, broadcast, FakeStore(), collaborators="fake")
    resume = tmp_path / "r.txt"
    resume.write_text("Jane Doe Python", encoding="utf-8")
    await p.extract_resume(str(resume))
    ctx = [e for e in events if e["type"] == "context_updated"][0]
    assert ctx["payload"]["resume_chars"] > 0
    await p.update_context("", "Acme backend role")
    content = p._context.build_messages("Tell me about yourself")[0]["content"]
    assert "Jane Doe Python" in content
    assert "Acme backend role" in content


@pytest.mark.asyncio
async def test_cloud_stt_fallback_warning(tmp_path, monkeypatch):
    monkeypatch.setenv("AIA_USER_DATA", str(tmp_path))
    user = tmp_path / "config.json"
    user.write_text('{"stt": {"engine": "cloud", "cloud_provider": "deepgram"}}', encoding="utf-8")
    cfg = load_config(Path("backend/config/defaults.json"), user, None)
    assert cfg.stt.engine == "local"
    events = []

    async def broadcast(msg):
        events.append(msg)

    p = Pipeline(cfg, broadcast, FakeStore(), collaborators="fake")
    assert "STT_CLOUD_FALLBACK" in p._status_payload()["warnings"]
