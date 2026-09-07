from __future__ import annotations

import logging

import websockets
from websockets.asyncio.server import Server, ServerConnection

from backend.server.events import make_event, parse_command

logger = logging.getLogger(__name__)

_COMMANDS = {
    "start_listening",
    "stop_listening",
    "update_context",
    "update_config",
    "manual_answer_request",
    "extract_resume",
    "list_history",
    "list_audio_devices",
}


class WsServer:
    def __init__(self, host: str, port: int, pipeline):
        if host != "127.0.0.1":
            raise ValueError("WsServer host must be 127.0.0.1")
        self._host = host
        self._port = port
        self.pipeline = pipeline
        self._clients: set[ServerConnection] = set()
        self._server: Server | None = None

    async def start(self) -> None:
        self._server = await websockets.serve(self._handler, self._host, self._port)
        logger.info("websocket listening on ws://%s:%s", self._host, self._port)

    async def stop(self) -> None:
        if self._server is None:
            return
        self._server.close()
        await self._server.wait_closed()
        self._server = None
        self._clients.clear()

    async def broadcast(self, message: dict) -> None:
        raw = make_event(message.get("type", ""), message.get("payload"))
        stale: list[ServerConnection] = []
        for client in list(self._clients):
            try:
                await client.send(raw)
            except Exception:
                stale.append(client)
        for client in stale:
            self._clients.discard(client)

    async def _handler(self, websocket: ServerConnection) -> None:
        self._clients.add(websocket)
        try:
            if self.pipeline is not None:
                await self.pipeline._emit_status()
            async for raw in websocket:
                text = raw if isinstance(raw, str) else raw.decode("utf-8")
                await self._dispatch(text)
        finally:
            self._clients.discard(websocket)

    async def _dispatch(self, raw: str) -> None:
        try:
            command = parse_command(raw)
        except ValueError as exc:
            await self.broadcast(
                {
                    "type": "error",
                    "payload": {"code": "UNKNOWN_COMMAND", "message": str(exc), "fatal": False},
                }
            )
            return
        cmd_type = command["type"]
        if cmd_type not in _COMMANDS:
            await self.broadcast(
                {
                    "type": "error",
                    "payload": {
                        "code": "UNKNOWN_COMMAND",
                        "message": f"unknown command: {cmd_type}",
                        "fatal": False,
                    },
                }
            )
            return
        if self.pipeline is None:
            return
        payload = command.get("payload") if isinstance(command.get("payload"), dict) else {}
        try:
            await self._run_command(cmd_type, payload)
        except Exception as exc:
            if self.pipeline is not None:
                await self.pipeline._emit_error("UNKNOWN_COMMAND", str(exc), fatal=False)

    async def _run_command(self, cmd_type: str, payload: dict) -> None:
        pipeline = self.pipeline
        if cmd_type == "start_listening":
            await pipeline.start_listening()
        elif cmd_type == "stop_listening":
            await pipeline.stop_listening()
        elif cmd_type == "update_context":
            await pipeline.update_context(
                resume_text=str(payload.get("resume_text", "")),
                job_description=str(payload.get("job_description", "")),
            )
        elif cmd_type == "update_config":
            await pipeline.update_config(payload)
        elif cmd_type == "manual_answer_request":
            await pipeline.manual_answer_request()
        elif cmd_type == "extract_resume":
            await pipeline.extract_resume(str(payload.get("path", "")))
        elif cmd_type == "list_history":
            await pipeline.list_history()
        elif cmd_type == "list_audio_devices":
            await pipeline.emit_audio_devices()
