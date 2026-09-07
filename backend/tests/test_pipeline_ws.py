import asyncio
import json
from pathlib import Path

import pytest
import websockets

from backend.config.loader import load_config, merge_user_config
from backend.pipeline import Pipeline
from backend.server.ws_server import WsServer
from backend.tests.test_pipeline import FakeStore


async def _recv_until(ws, pred, timeout=2.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise TimeoutError("timed out waiting for websocket message")
        obj = json.loads(await asyncio.wait_for(ws.recv(), timeout=remaining))
        if pred(obj):
            return obj


@pytest.mark.asyncio
async def test_start_listening_status(tmp_path):
    cfg = load_config(Path("backend/config/defaults.json"), tmp_path / "no.json", None)
    cfg = merge_user_config(cfg, {"server": {"port": 18765}})
    store = FakeStore()
    server = WsServer(cfg.server.host, cfg.server.port, pipeline=None)

    async def broadcast(msg):
        await server.broadcast(msg)

    pipeline = Pipeline(cfg, broadcast, store, collaborators="fake")
    server.pipeline = pipeline
    await server.start()
    try:
        uri = f"ws://{cfg.server.host}:{cfg.server.port}"
        async with websockets.connect(uri) as ws:
            first = json.loads(await asyncio.wait_for(ws.recv(), timeout=2))
            assert first["type"] == "status"
            await ws.send(json.dumps({"type": "start_listening"}))
            got = await _recv_until(ws, lambda m: m["type"] == "status")
            assert got["payload"]["state"] == "listening"
            await ws.send(json.dumps({"type": "not_a_command"}))
            err = await _recv_until(ws, lambda m: m["type"] == "error")
            assert err["payload"]["code"] == "UNKNOWN_COMMAND"
    finally:
        await pipeline.stop_listening()
        await server.stop()
