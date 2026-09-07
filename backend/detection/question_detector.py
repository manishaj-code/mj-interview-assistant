from __future__ import annotations

import re
import threading
from dataclasses import dataclass

from backend.config.schema import QuestionDetectionConfig
from backend.stt.transcriber import TranscriptEvent

_QUESTION_PREFIXES = (
    "walk me through",
    "walk us through",
    "tell me",
    "tell us",
    "talk about",
    "can you",
    "could you",
    "would you",
    "have you",
    "do you",
    "did you",
    "are you",
    "give me",
    "give an",
    "share an",
    "share a",
    "how about",
    "what about",
    "describe",
    "explain",
    "what",
    "why",
    "how",
    "when",
    "where",
    "who",
    "which",
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class DetectedQuestion:
    question_text: str
    timestamp_ms: int


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _is_lexical_question(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if stripped.endswith("?"):
        return True
    lower = stripped.casefold()
    padded = f" {lower} "
    return any(lower.startswith(prefix) or f" {prefix} " in padded for prefix in _QUESTION_PREFIXES)


def _looks_complete(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if stripped.endswith("?"):
        return True
    return len(stripped.split()) >= 4 and _is_lexical_question(stripped)


def _merge_utterance(prev: str, incoming: str) -> str:
    a = prev.strip()
    b = incoming.strip()
    if not a:
        return b
    al, bl = a.casefold(), b.casefold()
    if bl.startswith(al) or al.startswith(bl) or al in bl or bl in al:
        return b if len(b) >= len(a) else a
    return f"{a} {b}".strip()


def split_questions(text: str) -> list[str]:
    stripped = text.strip()
    if not stripped:
        return []
    parts = [p.strip() for p in _SENTENCE_SPLIT.split(stripped) if p.strip()]
    if len(parts) <= 1:
        return [stripped]
    found = [p for p in parts if _is_lexical_question(p)]
    return found or [stripped]


class QuestionDetector:
    def __init__(self, config: QuestionDetectionConfig, classify_fn=None):
        self._config = config
        self._classify_fn = classify_fn
        self._display = ""
        self._utterance = ""
        self._last_speech_ms: int | None = None
        self._awaiting_silence = False
        self._last_emitted_norm: str | None = None
        self._last_emitted_ms: int | None = None
        self._pending: list[DetectedQuestion] = []
        self._lock = threading.Lock()

    def on_transcript(self, event: TranscriptEvent) -> DetectedQuestion | None:
        incoming = event.text.strip()
        if not incoming:
            return None
        with self._lock:
            if not event.is_final:
                self._display = incoming
                self._utterance = incoming
                self._last_speech_ms = event.timestamp_ms
                self._awaiting_silence = True
                return None
            if (
                self._awaiting_silence
                and self._utterance
                and self._last_speech_ms is not None
                and event.timestamp_ms - self._last_speech_ms <= self._config.silence_gap_ms + 200
            ):
                self._utterance = _merge_utterance(self._utterance, incoming)
            else:
                self._utterance = incoming
            self._display = self._utterance
            self._last_speech_ms = event.timestamp_ms
            self._awaiting_silence = True
        return None

    def on_silence(self, now_ms: int) -> DetectedQuestion | None:
        with self._lock:
            if not self._awaiting_silence or not self._utterance or self._last_speech_ms is None:
                return None
            if now_ms - self._last_speech_ms < self._config.silence_gap_ms:
                return None
            utterance = self._utterance
            speech_ms = self._last_speech_ms
            self._awaiting_silence = False
        if not self._is_question(utterance):
            return None
        questions = [q for q in split_questions(utterance) if _looks_complete(q)]
        if not questions:
            return None
        emitted: list[DetectedQuestion] = []
        with self._lock:
            for question in questions:
                norm = _normalize(question)
                if (
                    self._last_emitted_norm == norm
                    and self._last_emitted_ms is not None
                    and now_ms - self._last_emitted_ms <= 5000
                ):
                    continue
                self._last_emitted_norm = norm
                self._last_emitted_ms = now_ms
                emitted.append(DetectedQuestion(question, speech_ms))
            self._utterance = ""
            self._display = ""
            if len(emitted) > 1:
                self._pending.extend(emitted[1:])
        return emitted[0] if emitted else None

    def pop_pending(self) -> DetectedQuestion | None:
        with self._lock:
            if not self._pending:
                return None
            return self._pending.pop(0)

    def current_buffer_text(self) -> str:
        with self._lock:
            return self._utterance or self._display

    def reset(self) -> None:
        with self._lock:
            self._display = ""
            self._utterance = ""
            self._last_speech_ms = None
            self._awaiting_silence = False
            self._last_emitted_norm = None
            self._last_emitted_ms = None
            self._pending.clear()

    def _is_question(self, text: str) -> bool:
        if _is_lexical_question(text):
            return True
        if not self._config.use_llm_fallback_classifier or self._classify_fn is None:
            return False
        try:
            return bool(self._classify_fn(text))
        except Exception:
            return False
