from backend.config.schema import QuestionDetectionConfig
from backend.detection.question_detector import QuestionDetector, DetectedQuestion
from backend.stt.transcriber import TranscriptEvent

CFG = QuestionDetectionConfig(silence_gap_ms=800, use_llm_fallback_classifier=False)


def final(text, ts):
    return TranscriptEvent(text=text, is_final=True, timestamp_ms=ts)


def test_question_word_plus_silence_detects():
    d = QuestionDetector(CFG)
    assert d.on_transcript(final("Tell me about a time you failed", 1000)) is None
    got = d.on_silence(1900)
    assert isinstance(got, DetectedQuestion)
    assert "failed" in got.question_text.lower()


def test_statement_without_silence_does_not_detect():
    d = QuestionDetector(CFG)
    assert d.on_transcript(final("I worked at Acme for five years.", 1000)) is None
    assert d.on_silence(1200) is None  # 200ms < 800ms


def test_duplicate_within_5s_ignored():
    d = QuestionDetector(CFG)
    d.on_transcript(final("What is your strength?", 1000))
    first = d.on_silence(2000)
    assert first is not None
    d.on_transcript(final("What is your strength?", 2500))
    assert d.on_silence(3500) is None


def test_manual_buffer():
    d = QuestionDetector(CFG)
    d.on_transcript(final("Can you explain Redis?", 1))
    assert "Redis" in d.current_buffer_text()


def test_consecutive_finals_join_before_silence():
    d = QuestionDetector(CFG)
    d.on_transcript(final("Can you tell me", 1000))
    d.on_transcript(final("about your experience", 1300))
    got = d.on_silence(2200)
    assert got is not None
    assert "can you tell me about your experience" in got.question_text.lower()


def test_splits_multiple_questions_in_one_utterance():
    d = QuestionDetector(CFG)
    d.on_transcript(final("What is your strength? What is your weakness?", 1000))
    first = d.on_silence(1900)
    second = d.pop_pending()
    assert first is not None
    assert second is not None
    assert "strength" in first.question_text.lower()
    assert "weakness" in second.question_text.lower()
    assert d.pop_pending() is None


def test_second_question_after_first_still_detects():
    d = QuestionDetector(CFG)
    d.on_transcript(final("What is your strength?", 1000))
    assert d.on_silence(1900) is not None
    d.on_transcript(final("Why do you want this job?", 4000))
    got = d.on_silence(5000)
    assert got is not None
    assert "why do you want this job" in got.question_text.lower()


def test_partial_plus_silence_detects():
    d = QuestionDetector(CFG)
    partial = TranscriptEvent(text="What is your strength?", is_final=False, timestamp_ms=1000)
    assert d.on_transcript(partial) is None
    got = d.on_silence(1900)
    assert got is not None
    assert "strength" in got.question_text.lower()


def test_short_incomplete_partial_not_detected():
    d = QuestionDetector(CFG)
    d.on_transcript(TranscriptEvent(text="What is", is_final=False, timestamp_ms=1000))
    assert d.on_silence(1900) is None
