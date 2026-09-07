import numpy as np
import pytest

from backend.audio.capture import AudioChunk
from backend.config.schema import SttConfig
from backend.stt.transcriber import Transcriber, TranscriptEvent


def _chunk(text_marker: bytes = b"\x00\x01"):
    pcm = (text_marker * 480)[:960]  # 30ms at 16k s16le = 960 bytes
    if len(pcm) < 960:
        pcm = pcm + b"\x00" * (960 - len(pcm))
    return AudioChunk(pcm=pcm, sample_rate=16000, timestamp_ms=1_700_000_000_000)


@pytest.mark.asyncio
async def test_fake_emits_partial_then_final():
    cfg = SttConfig(engine="local", local_model_size="small", cloud_provider=None)
    t = Transcriber(cfg, engine_impl="fake")
    await t.start()
    events = []
    for _ in range(12):
        ev = await t.process_chunk(_chunk())
        if ev:
            events.append(ev)
    await t.stop()
    assert any(e.is_final is False for e in events)
    assert any(e.is_final is True for e in events)
    assert all(e.text.strip() for e in events)
    assert all(isinstance(e, TranscriptEvent) for e in events)


@pytest.mark.asyncio
async def test_fake_does_not_emit_empty():
    cfg = SttConfig(engine="local", local_model_size="small", cloud_provider=None)
    t = Transcriber(cfg, engine_impl="fake_silence")
    await t.start()
    ev = await t.process_chunk(_chunk())
    await t.stop()
    assert ev is None


def _loud(ts: int) -> AudioChunk:
    pcm = (np.ones(480, dtype=np.int16) * 8000).tobytes()
    return AudioChunk(pcm=pcm, sample_rate=16000, timestamp_ms=ts)


def _quiet(ts: int) -> AudioChunk:
    return AudioChunk(pcm=b"\x00" * 960, sample_rate=16000, timestamp_ms=ts)


@pytest.mark.asyncio
async def test_local_does_not_transcribe_until_silence():
    cfg = SttConfig(engine="local", local_model_size="small", cloud_provider=None)
    t = Transcriber(cfg, engine_impl="auto")
    t._model = object()
    calls = []

    def fake_transcribe(pcm, sr):
        calls.append(len(pcm))
        return "what is your strength?"

    t._transcribe_pcm = fake_transcribe
    events = []
    ts = 1000
    for _ in range(10):
        ev = await t.process_chunk(_loud(ts))
        if ev:
            events.append(ev)
        ts += 30
    assert calls == []
    for _ in range(16):
        ev = await t.process_chunk(_quiet(ts))
        if ev:
            events.append(ev)
        ts += 30
    assert calls
    assert any(e.is_final is False for e in events)
    assert any(e.is_final is True for e in events)
    assert events[0].text == "what is your strength?"
    await t.stop()
