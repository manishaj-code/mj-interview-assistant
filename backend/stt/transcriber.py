from __future__ import annotations

import asyncio
from dataclasses import dataclass

import numpy as np

from backend.audio.capture import AudioChunk
from backend.config.schema import SttConfig


@dataclass(frozen=True)
class TranscriptEvent:
    text: str
    is_final: bool
    timestamp_ms: int


class Transcriber:
    def __init__(self, config: SttConfig, engine_impl: str = "auto", deepgram_api_key: str | None = None):
        self._config = config
        self._engine_impl = engine_impl
        self._deepgram_key = deepgram_api_key
        self._chunk_count = 0
        self._model = None
        self._deepgram = None
        self.init_warning: str | None = None
        self._pcm = bytearray()
        self._pending: list[TranscriptEvent] = []
        self._last_timestamp_ms = 0
        self._last_sample_rate = 16000
        self._speech_seen = False
        self._last_loud_ms: int | None = None
        self._utterance_start_ms: int | None = None

    async def start(self) -> None:
        if self._engine_impl != "auto":
            return
        if self._deepgram_key:
            try:
                from backend.stt.deepgram_engine import DeepgramEngine

                self._deepgram = DeepgramEngine(self._deepgram_key)
                await self._deepgram.start()
                return
            except Exception as exc:
                self.init_warning = f"STT_INIT_FAILED: {exc}"
                self._deepgram = None

        def load():
            from faster_whisper import WhisperModel

            return WhisperModel(
                self._config.local_model_size,
                device="cpu",
                compute_type="int8",
            )

        try:
            self._model = await asyncio.to_thread(load)
        except Exception as exc:
            raise RuntimeError(f"STT_INIT_FAILED: {exc}") from exc

    async def stop(self) -> None:
        self._pcm.clear()
        self._chunk_count = 0
        self._pending.clear()
        self._speech_seen = False
        self._last_loud_ms = None
        self._utterance_start_ms = None
        if self._deepgram is not None:
            await self._deepgram.stop()
            self._deepgram = None

    async def process_chunk(self, chunk: AudioChunk) -> TranscriptEvent | None:
        if self._pending:
            if self._engine_impl == "auto":
                self._buffer_chunk(chunk)
            return self._pending.pop(0)
        if self._engine_impl == "fake_silence":
            return None
        if self._engine_impl == "fake":
            return self._fake_event(chunk)
        if self._deepgram is not None:
            await self._deepgram.send_pcm(chunk.pcm)
            event = await self._deepgram.poll()
            if event is None:
                return None
            return TranscriptEvent(event.text, event.is_final, chunk.timestamp_ms)
        if self._engine_impl == "auto" and self._model is not None:
            return await self._process_local(chunk)
        return None

    def _buffer_chunk(self, chunk: AudioChunk) -> None:
        self._pcm.extend(chunk.pcm)
        self._last_timestamp_ms = chunk.timestamp_ms
        self._last_sample_rate = chunk.sample_rate

    def _fake_event(self, chunk: AudioChunk) -> TranscriptEvent | None:
        self._chunk_count += 1
        if self._chunk_count % 10 == 0:
            return _nonempty(TranscriptEvent("hello world", True, chunk.timestamp_ms))
        if self._chunk_count % 3 == 0:
            return _nonempty(TranscriptEvent("hello", False, chunk.timestamp_ms))
        return None

    async def _process_local(self, chunk: AudioChunk) -> TranscriptEvent | None:
        self._buffer_chunk(chunk)
        rms = _chunk_rms(chunk.pcm)
        now = chunk.timestamp_ms
        if rms >= _RMS_SPEECH:
            self._speech_seen = True
            self._last_loud_ms = now
            if self._utterance_start_ms is None:
                self._utterance_start_ms = now
            if now - self._utterance_start_ms >= _MAX_UTTERANCE_MS:
                return await self._flush_local(chunk)
            return None
        if not self._speech_seen:
            self._pcm.clear()
            return None
        if self._last_loud_ms is None or now - self._last_loud_ms < _SILENCE_FLUSH_MS:
            return None
        return await self._flush_local(chunk)

    async def _flush_local(self, chunk: AudioChunk) -> TranscriptEvent | None:
        window = bytes(self._pcm)
        self._pcm.clear()
        self._speech_seen = False
        self._last_loud_ms = None
        self._utterance_start_ms = None
        min_bytes = int(chunk.sample_rate * 2 * 0.25)
        if len(window) < min_bytes:
            return None
        text = await asyncio.to_thread(self._transcribe_pcm, window, chunk.sample_rate)
        text = (text or "").strip()
        if not text:
            return None
        self._pending.append(TranscriptEvent(text, True, chunk.timestamp_ms))
        return TranscriptEvent(text, False, chunk.timestamp_ms)

    def _transcribe_pcm(self, pcm: bytes, sample_rate: int) -> str:
        audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        if float(np.sqrt(np.mean(np.square(audio)))) < 0.012:
            return ""
        segments, _info = self._model.transcribe(
            audio,
            language="en",
            beam_size=1,
            vad_filter=True,
            condition_on_previous_text=False,
            no_speech_threshold=0.7,
        )
        text = " ".join(segment.text.strip() for segment in segments).strip()
        if _looks_like_hallucination(text):
            return ""
        return text


_RMS_SPEECH = 0.012
_SILENCE_FLUSH_MS = 450
_MAX_UTTERANCE_MS = 12000

_HALLUCINATION_MARKERS = (
    "bye. bye",
    "bye bye",
    "thank you for watching",
    "thanks for watching",
    "we'll see you",
    "subscribe",
)


def _chunk_rms(pcm: bytes) -> float:
    if not pcm:
        return 0.0
    audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    return float(np.sqrt(np.mean(np.square(audio))))


def _looks_like_hallucination(text: str) -> bool:
    lower = text.casefold()
    if lower.count("bye") >= 3:
        return True
    return any(marker in lower for marker in _HALLUCINATION_MARKERS)


def _nonempty(event: TranscriptEvent) -> TranscriptEvent | None:
    text = event.text.strip()
    if not text:
        return None
    if text == event.text:
        return event
    return TranscriptEvent(text=text, is_final=event.is_final, timestamp_ms=event.timestamp_ms)
