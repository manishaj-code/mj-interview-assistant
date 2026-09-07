from __future__ import annotations

import asyncio
import inspect
import json
import os
import threading
import time
from pathlib import Path

from backend.audio.capture import AudioCapture, AudioCaptureError
from backend.audio.devices import list_loopback_devices
from backend.config.loader import merge_user_config
from backend.config.schema import AppConfig, AudioConfig
from backend.context.context_manager import ContextManager
from backend.context.pdf_extract import extract_resume_text
from backend.detection.question_detector import DetectedQuestion, QuestionDetector
from backend.llm.claude_client import ClaudeClient, LlmError, has_llm_key, select_transport
from backend.stt.transcriber import Transcriber


def _user_config_path() -> Path:
    return Path(os.environ.get("AIA_USER_DATA", "data")) / "config.json"


def _stt_cloud_warnings(config: AppConfig, user_path: Path) -> list[str]:
    if config.deepgram_api_key:
        return []
    if not user_path.exists():
        return []
    try:
        data = json.loads(user_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(data, dict) and (data.get("stt") or {}).get("engine") == "cloud":
        return ["STT_CLOUD_FALLBACK"]
    return []


class Pipeline:
    def __init__(self, config: AppConfig, broadcast, store, collaborators: str = "auto"):
        self._config = config
        self._broadcast = broadcast
        self._store = store
        self._state = "idle"
        self._queue: asyncio.Queue | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task | None = None
        self._question_task: asyncio.Task | None = None
        self._question_q: asyncio.Queue | None = None
        self._silence_thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._resume_text = ""
        self._job_description = config.context.job_description or ""
        self._user_config_path = _user_config_path()
        self._warnings = _stt_cloud_warnings(config, self._user_config_path)
        self._context = ContextManager(config.context, config.llm.answer_style)
        if self._job_description:
            self._context.set_job_description(self._job_description)

        if collaborators == "fake":
            audio_cfg = AudioConfig(input_device="fake", sample_rate=16000, chunk_ms=30)
            self._capture = AudioCapture(audio_cfg, source="fake")
            self._transcriber = Transcriber(config.stt, engine_impl="fake")
            self._llm = ClaudeClient(config.llm, api_key=config.anthropic_api_key or "x", transport="fake")
        else:
            self._capture = AudioCapture(config.audio, source="loopback")
            self._transcriber = Transcriber(config.stt, engine_impl="auto", deepgram_api_key=config.deepgram_api_key)
            transport, api_key = select_transport(
                config.groq_api_key, config.gemini_api_key, config.anthropic_api_key
            )
            self._llm = ClaudeClient(config.llm, api_key=api_key, transport=transport)

        self._detector = QuestionDetector(
            config.question_detection,
            classify_fn=self._classify_sync if config.question_detection.use_llm_fallback_classifier else None,
        )

    def state(self) -> str:
        return self._state

    def _status_payload(self) -> dict:
        return {
            "state": self._state,
            "warnings": list(self._warnings),
            "missing_api_key": not has_llm_key(
                self._config.groq_api_key, self._config.gemini_api_key, self._config.anthropic_api_key
            ),
        }

    async def _emit(self, type: str, payload: dict | None = None) -> None:
        message = {"type": type, "payload": payload if payload is not None else {}}
        result = self._broadcast(message)
        if inspect.isawaitable(result):
            await result

    async def _emit_status(self) -> None:
        await self._emit("status", self._status_payload())

    async def _emit_error(self, code: str, message: str, fatal: bool = False) -> None:
        await self._emit("error", {"code": code, "message": message, "fatal": fatal})
        if fatal:
            self._state = "error"

    def _classify_sync(self, text: str) -> bool:
        if self._loop is None or not self._loop.is_running():
            return False
        try:
            future = asyncio.run_coroutine_threadsafe(self._llm.classify_is_question(text), self._loop)
            return bool(future.result(timeout=15))
        except Exception:
            return False

    async def start_listening(self) -> None:
        if self._state == "listening":
            await self._emit_status()
            return
        self._loop = asyncio.get_running_loop()
        self._queue = asyncio.Queue()
        self._stop.clear()
        self._detector.reset()
        try:
            await self._transcriber.start()
        except RuntimeError as exc:
            await self._emit_error("STT_INIT_FAILED", str(exc), fatal=True)
            return
        if self._transcriber.init_warning:
            await self._emit_error("STT_INIT_FAILED", self._transcriber.init_warning, fatal=False)
        try:
            self._capture.start(self._queue)
        except AudioCaptureError as exc:
            await self._transcriber.stop()
            self._state = "idle"
            await self._emit_error(exc.code, exc.message, fatal=False)
            await self._emit_status()
            return
        self._store.start_session()
        self._state = "listening"
        await self._emit_status()
        self._question_q = asyncio.Queue()
        self._task = asyncio.create_task(self._run_loop())
        self._question_task = asyncio.create_task(self._question_worker())
        self._silence_thread = threading.Thread(target=self._silence_loop, daemon=True)
        self._silence_thread.start()

    async def stop_listening(self) -> None:
        was_listening = self._state == "listening"
        self._state = "idle"
        self._stop.set()
        self._llm.cancel_current()
        self._capture.stop()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
        if self._question_task is not None:
            self._question_task.cancel()
            try:
                await self._question_task
            except (asyncio.CancelledError, Exception):
                pass
            self._question_task = None
        self._question_q = None
        if self._silence_thread is not None:
            self._silence_thread.join(timeout=1.0)
            self._silence_thread = None
        await self._transcriber.stop()
        if was_listening or True:
            await self._emit_status()

    async def _run_loop(self) -> None:
        assert self._queue is not None
        while not self._stop.is_set() and self._state == "listening":
            try:
                chunk = await asyncio.wait_for(self._queue.get(), timeout=0.05)
            except asyncio.TimeoutError:
                continue
            event = await self._transcriber.process_chunk(chunk)
            if event is None:
                continue
            kind = "transcript_final" if event.is_final else "transcript_partial"
            await self._emit(kind, {"text": event.text, "timestamp": event.timestamp_ms})
            self._detector.on_transcript(event)

    def _enqueue_question(self, detected: DetectedQuestion) -> None:
        if self._question_q is None:
            return
        self._question_q.put_nowait(detected)

    def _silence_loop(self) -> None:
        while not self._stop.is_set() and self._state == "listening":
            time.sleep(0.05)
            if self._loop is None:
                continue
            detected = self._detector.on_silence(int(time.time() * 1000))
            if detected is not None:
                self._loop.call_soon_threadsafe(self._enqueue_question, detected)
            while True:
                pending = self._detector.pop_pending()
                if pending is None:
                    break
                self._loop.call_soon_threadsafe(self._enqueue_question, pending)

    async def _question_worker(self) -> None:
        assert self._question_q is not None
        while not self._stop.is_set() and self._state == "listening":
            try:
                detected = await asyncio.wait_for(self._question_q.get(), timeout=0.1)
            except asyncio.TimeoutError:
                continue
            try:
                await self._handle_question(detected)
            except Exception:
                continue

    async def _handle_question(self, detected: DetectedQuestion) -> None:
        await self._emit(
            "question_detected",
            {"question_text": detected.question_text, "timestamp": detected.timestamp_ms},
        )
        if not has_llm_key(
            self._config.groq_api_key, self._config.gemini_api_key, self._config.anthropic_api_key
        ) and self._llm._transport != "fake":
            await self._emit_error(
                "MISSING_API_KEY",
                "Add GROQ_API_KEY or GEMINI_API_KEY to .env.",
                fatal=False,
            )
            return
        started = time.time()
        messages = self._context.build_messages(detected.question_text)
        parts: list[str] = []
        seq = 1
        try:
            async for token in self._llm.stream_answer(self._context.system_prompt, messages):
                await self._emit("answer_token", {"token": token, "seq": seq})
                seq += 1
                parts.append(token)
        except LlmError as exc:
            await self._emit_error(exc.code, exc.message, fatal=False)
            return
        full_answer = "".join(parts)
        duration_ms = int((time.time() - started) * 1000)
        await self._emit(
            "answer_complete",
            {
                "question_text": detected.question_text,
                "full_answer": full_answer,
                "duration_ms": duration_ms,
            },
        )
        self._store.append(
            question_text=detected.question_text,
            full_answer=full_answer,
            timestamp_ms=detected.timestamp_ms,
            duration_ms=duration_ms,
        )
        self._context.add_qa_pair(detected.question_text, full_answer)

    async def update_context(self, resume_text: str, job_description: str) -> None:
        if resume_text == "" and self._resume_text:
            pass
        else:
            self._resume_text = resume_text
            self._context.set_resume(resume_text)
        self._job_description = job_description
        self._context.set_job_description(job_description)
        await self._emit_context_updated()

    async def extract_resume(self, path: str) -> None:
        try:
            text = extract_resume_text(Path(path))
        except Exception as exc:
            await self._emit_error("RESUME_PARSE_FAILED", str(exc), fatal=False)
            return
        self._resume_text = text
        self._context.set_resume(text)
        await self._emit_context_updated()

    async def _emit_context_updated(self) -> None:
        preview = self._resume_text[:200]
        await self._emit(
            "context_updated",
            {
                "resume_chars": len(self._resume_text),
                "job_description_chars": len(self._job_description),
                "resume_preview": preview,
            },
        )

    async def update_config(self, patch: dict) -> AppConfig:
        if isinstance(patch.get("server"), dict) and (
            "port" in patch["server"] or "host" in patch["server"]
        ):
            await self._emit_error("CONFIG_INVALID", "port changes need app restart", fatal=False)
            patch = {k: v for k, v in patch.items() if k != "server"}
        self._config = merge_user_config(self._config, patch)
        self._user_config_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "llm": {
                "model": self._config.llm.model,
                "max_tokens": self._config.llm.max_tokens,
                "temperature": self._config.llm.temperature,
                "answer_style": self._config.llm.answer_style,
            },
            "stt": {
                "engine": self._config.stt.engine,
                "local_model_size": self._config.stt.local_model_size,
                "cloud_provider": self._config.stt.cloud_provider,
            },
            "question_detection": {
                "silence_gap_ms": self._config.question_detection.silence_gap_ms,
                "use_llm_fallback_classifier": self._config.question_detection.use_llm_fallback_classifier,
            },
            "context": {
                "max_history_pairs": self._config.context.max_history_pairs,
                "resume_path": self._config.context.resume_path,
                "job_description": self._config.context.job_description,
            },
            "audio": {
                "input_device": self._config.audio.input_device,
                "sample_rate": self._config.audio.sample_rate,
                "chunk_ms": self._config.audio.chunk_ms,
            },
            "overlay": {
                "always_on_top": self._config.overlay.always_on_top,
                "content_protection": self._config.overlay.content_protection,
                "opacity": self._config.overlay.opacity,
                "hotkey_toggle_visibility": self._config.overlay.hotkey_toggle_visibility,
                "hotkey_panic_hide": self._config.overlay.hotkey_panic_hide,
            },
            "storage": {
                "session_history_enabled": self._config.storage.session_history_enabled,
                "session_history_path": self._config.storage.session_history_path,
            },
            "server": {
                "host": self._config.server.host,
                "port": self._config.server.port,
            },
        }
        self._user_config_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        self._context.set_answer_style(self._config.llm.answer_style)
        if hasattr(self._store, "set_enabled"):
            self._store.set_enabled(self._config.storage.session_history_enabled)
        if (patch.get("stt") or {}).get("engine") == "cloud" and not self._config.deepgram_api_key:
            if "STT_CLOUD_FALLBACK" not in self._warnings:
                self._warnings.append("STT_CLOUD_FALLBACK")
        await self._emit_status()
        return self._config

    async def manual_answer_request(self) -> None:
        text = self._detector.current_buffer_text().strip()
        if not text:
            await self._emit_error("NO_TRANSCRIPT_BUFFER", "No transcript buffer.", fatal=False)
            return
        await self._handle_question(DetectedQuestion(text, int(time.time() * 1000)))

    async def list_history(self) -> dict:
        payload = {"sessions": self._store.list_sessions()}
        await self._emit("history_data", payload)
        return payload

    def list_audio_devices(self) -> list[dict]:
        return list_loopback_devices()

    async def emit_audio_devices(self) -> None:
        await self._emit("audio_devices", {"devices": self.list_audio_devices()})
