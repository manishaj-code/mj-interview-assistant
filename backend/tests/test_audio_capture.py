import asyncio
import time

import pytest

from backend.audio.capture import AudioCapture, AudioCaptureError, AudioChunk
from backend.config.schema import AudioConfig


def _cfg(device="fake"):
    return AudioConfig(input_device=device, sample_rate=16000, chunk_ms=30)


@pytest.mark.asyncio
async def test_fake_capture_emits_pcm_chunks():
    cap = AudioCapture(_cfg("fake"), source="fake")
    q: asyncio.Queue[AudioChunk] = asyncio.Queue()
    cap.start(q)
    chunk = await asyncio.wait_for(q.get(), timeout=1)
    cap.stop()
    assert isinstance(chunk, AudioChunk)
    assert chunk.sample_rate == 16000
    assert len(chunk.pcm) == 16000 * 30 // 1000 * 2  # s16le mono
    assert chunk.timestamp_ms <= int(time.time() * 1000)


def test_missing_device_raises():
    cap = AudioCapture(_cfg("does-not-exist"), source="fake")
    with pytest.raises(AudioCaptureError) as ei:
        cap.start(asyncio.Queue())
    assert ei.value.code == "AUDIO_DEVICE_NOT_FOUND"
    assert cap.is_running() is False
