from __future__ import annotations

import asyncio
import sys
import threading
import time
from dataclasses import dataclass

import numpy as np

from backend.config.schema import AudioConfig


@dataclass(frozen=True)
class AudioChunk:
    pcm: bytes
    sample_rate: int
    timestamp_ms: int


class AudioCaptureError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class AudioCapture:
    def __init__(self, config: AudioConfig, source: str = "loopback"):
        self._config = config
        self._source = source
        self._running = False
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._queue: asyncio.Queue[AudioChunk] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._pa = None
        self._stream = None
        self._start_error: Exception | None = None
        self._ready = threading.Event()

    def start(self, queue: asyncio.Queue[AudioChunk]) -> None:
        if self._source == "fake":
            if self._config.input_device != "fake":
                raise AudioCaptureError(
                    "AUDIO_DEVICE_NOT_FOUND",
                    "Could not initialize audio loopback device.",
                )
            self._queue = queue
            self._stop.clear()
            self._running = True
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                self._loop = None
            self._thread = threading.Thread(target=self._run_fake, daemon=True)
            self._thread.start()
            return

        self._queue = queue
        self._stop.clear()
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None
        try:
            if sys.platform == "win32":
                self._start_windows_loopback()
            else:
                self._start_sounddevice()
        except AudioCaptureError:
            raise
        except Exception as exc:
            self._cleanup_stream()
            raise AudioCaptureError(
                "AUDIO_DEVICE_NOT_FOUND",
                str(exc) or "Could not initialize audio loopback device.",
            ) from exc
        self._running = True

    def stop(self) -> None:
        self._stop.set()
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        self._cleanup_stream()

    def is_running(self) -> bool:
        return self._running

    def _enqueue(self, pcm: bytes) -> None:
        if not pcm or self._queue is None:
            return
        chunk = AudioChunk(
            pcm=pcm,
            sample_rate=self._config.sample_rate,
            timestamp_ms=int(time.time() * 1000),
        )
        try:
            if self._loop is not None:
                self._loop.call_soon_threadsafe(self._queue.put_nowait, chunk)
            else:
                self._queue.put_nowait(chunk)
        except RuntimeError:
            return

    def _run_fake(self) -> None:
        frames = self._config.sample_rate * self._config.chunk_ms // 1000
        pcm = b"\x00" * (frames * 2)
        interval = self._config.chunk_ms / 1000.0
        while not self._stop.is_set():
            self._enqueue(pcm)
            self._stop.wait(interval)

    def _start_windows_loopback(self) -> None:
        self._start_error = None
        self._ready.clear()
        self._thread = threading.Thread(target=self._run_windows_loopback, daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=8):
            raise AudioCaptureError(
                "AUDIO_DEVICE_NOT_FOUND",
                "Could not initialize audio loopback device.",
            )
        if self._start_error is not None:
            raise self._start_error

    def _run_windows_loopback(self) -> None:
        import soundcard as sc  # noqa: F401 — COM must init on this thread

        com_owned = False
        if sys.platform == "win32":
            import ctypes

            hr = int(ctypes.windll.ole32.CoInitializeEx(None, 0x0))
            if hr < 0:
                hr = hr + 2**32
            if hr not in (0, 1):
                self._start_error = AudioCaptureError(
                    "AUDIO_DEVICE_NOT_FOUND",
                    f"Could not initialize audio loopback device ({hex(hr)}).",
                )
                self._ready.set()
                return
            com_owned = hr == 0
        recorder = None
        try:
            mic = _resolve_soundcard_loopback(self._config.input_device)
            dst_rate = self._config.sample_rate
            frames = max(1, int(dst_rate * self._config.chunk_ms / 1000))
            recorder = mic.recorder(samplerate=dst_rate, channels=1)
            recorder.__enter__()
            self._stream = recorder
            self._ready.set()
        except Exception as exc:
            self._start_error = AudioCaptureError(
                "AUDIO_DEVICE_NOT_FOUND",
                str(exc) or "Could not initialize audio loopback device.",
            )
            self._ready.set()
            if com_owned:
                import ctypes

                ctypes.windll.ole32.CoUninitialize()
            return

        try:
            while not self._stop.is_set() and recorder is not None:
                data = recorder.record(numframes=frames)
                samples = np.asarray(data, dtype=np.float32)
                if samples.ndim > 1:
                    samples = samples.mean(axis=1)
                pcm = np.clip(samples * 32767.0, -32768, 32767).astype(np.int16).tobytes()
                self._enqueue(pcm)
        except Exception:
            pass
        finally:
            if recorder is not None:
                try:
                    recorder.__exit__(None, None, None)
                except Exception:
                    pass
            self._stream = None
            if com_owned:
                import ctypes

                ctypes.windll.ole32.CoUninitialize()

    def _start_sounddevice(self) -> None:
        import sounddevice as sd

        from backend.audio.devices import list_loopback_devices

        device_id = _resolve_sounddevice_id(self._config.input_device, list_loopback_devices())
        dst_rate = self._config.sample_rate
        frames = max(1, int(dst_rate * self._config.chunk_ms / 1000))

        def callback(indata, frames_count, time_info, status):
            if self._stop.is_set():
                raise sd.CallbackStop
            pcm = np.ascontiguousarray(
                indata[:, 0] if indata.ndim > 1 else indata
            ).astype(np.int16).tobytes()
            self._enqueue(pcm)

        self._stream = sd.InputStream(
            samplerate=dst_rate,
            channels=1,
            dtype="int16",
            blocksize=frames,
            device=device_id,
            callback=callback,
        )
        self._stream.start()

    def _cleanup_stream(self) -> None:
        if self._stream is not None:
            try:
                stop = getattr(self._stream, "stop_stream", None) or getattr(self._stream, "stop", None)
                if stop:
                    stop()
                close = getattr(self._stream, "close", None)
                if close:
                    close()
            except Exception:
                pass
            self._stream = None
        if self._pa is not None:
            try:
                self._pa.terminate()
            except Exception:
                pass
            self._pa = None


def _resolve_soundcard_loopback(input_device: str):
    import soundcard as sc

    speakers = list(sc.all_speakers())
    loopbacks = list(sc.all_microphones(include_loopback=True))
    loopback_mics = [mic for mic in loopbacks if getattr(mic, "isloopback", False)]

    if input_device == "system_default_loopback":
        speaker = sc.default_speaker()
        return sc.get_microphone(id=str(speaker.id), include_loopback=True)

    for mic in loopback_mics:
        if mic.name == input_device or str(mic.id) == input_device:
            return mic
    for speaker in speakers:
        if speaker.name == input_device or str(speaker.id) == input_device:
            return sc.get_microphone(id=str(speaker.id), include_loopback=True)

    raise AudioCaptureError(
        "AUDIO_DEVICE_NOT_FOUND",
        "Could not initialize audio loopback device.",
    )


def _resolve_sounddevice_id(input_device: str, devices: list[dict]):
    if input_device == "system_default_loopback":
        for item in devices:
            if item.get("is_loopback") and item["id"] != "system_default_loopback":
                return item["id"]
        raise AudioCaptureError(
            "AUDIO_DEVICE_NOT_FOUND",
            "Could not initialize audio loopback device.",
        )
    for item in devices:
        if item["id"] == input_device or item["name"] == input_device:
            return item["id"]
    raise AudioCaptureError(
        "AUDIO_DEVICE_NOT_FOUND",
        "Could not initialize audio loopback device.",
    )
