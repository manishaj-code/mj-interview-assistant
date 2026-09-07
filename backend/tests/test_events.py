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
