from __future__ import annotations

import json
from typing import Any


def make_event(type: str, payload: dict | None = None) -> str:
    return json.dumps({"type": type, "payload": payload if payload is not None else {}}, separators=(",", ":"))


def parse_command(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("invalid json") from exc
    if not isinstance(parsed, dict) or not isinstance(parsed.get("type"), str) or not parsed["type"]:
        raise ValueError("missing type")
    return parsed
