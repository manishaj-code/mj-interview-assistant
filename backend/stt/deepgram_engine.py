from __future__ import annotations

import asyncio
import json
import os
from urllib.parse import urlencode

import websockets

from backend.stt.transcriber import TranscriptEvent


class DeepgramEngine:
    def __init__(self, api_key: str, sample_rate: int = 16000):
        self._api_key = api_key
        self._sample_rate = sample_rate
        self._ws = None
        self._pending: asyncio.Queue[TranscriptEvent] = asyncio.Queue()
        self._reader_task: asyncio.Task | None = None
        self._last_text = ""

    async def start(self) -> None:
        params = {
            "encoding": "linear16",
            "sample_rate": str(self._sample_rate),
            "channels": "1",
            "punctuate": "true",
            "interim_results": "true",
            "utterance_end_ms": "1000",
            "endpointing": "300",
            "language": os.environ.get("DEEPGRAM_LANGUAGE") or "en",
            "model": os.environ.get("DEEPGRAM_MODEL") or "nova-2",
        }
        if os.environ.get("DEEPGRAM_SMART_FORMAT", "true").lower() in {"1", "true", "yes"}:
            params["smart_format"] = "true"
        url = "wss://api.deepgram.com/v1/listen?" + urlencode(params)
        self._ws = await websockets.connect(
            url,
            additional_headers={"Authorization": f"Token {self._api_key}"},
        )
        self._reader_task = asyncio.create_task(self._read())

    async def send_pcm(self, pcm: bytes) -> None:
        if self._ws is None:
            return
        await self._ws.send(pcm)

    async def poll(self) -> TranscriptEvent | None:
        try:
            return self._pending.get_nowait()
        except asyncio.QueueEmpty:
            return None

    async def stop(self) -> None:
        if self._reader_task is not None:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except (asyncio.CancelledError, Exception):
                pass
            self._reader_task = None
        if self._ws is not None:
            await self._ws.close()
            self._ws = None

    async def _read(self) -> None:
        assert self._ws is not None
        async for raw in self._ws:
            try:
                data = json.loads(raw)
            except Exception:
                continue
            if data.get("type") == "UtteranceEnd":
                if self._last_text:
                    await self._pending.put(TranscriptEvent(self._last_text, True, 0))
                    self._last_text = ""
                continue
            alt = (((data.get("channel") or {}).get("alternatives") or [{}])[0])
            text = (alt.get("transcript") or "").strip()
            if not text:
                continue
            is_final = bool(data.get("speech_final") or data.get("is_final"))
            self._last_text = "" if is_final else text
            await self._pending.put(TranscriptEvent(text, is_final, 0))
