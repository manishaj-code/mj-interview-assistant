# Phase 3: Question Detection and LLM Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Stop after this phase.** Requires Phase 2 complete. Do not start Phase 4.

**Goal:** Detect a completed interviewer question and stream a Claude answer to the console, using resume/JD/history in the prompt.

**Architecture:** Layered `QuestionDetector` (silence → lexical → optional classifier). `ContextManager.build_messages` + system prompt. `ClaudeClient.stream_answer` yields text deltas. Console runner wires STT → detect → LLM.

**Tech Stack:** anthropic Python SDK, pytest, pytest-asyncio

**Spec:** [specs/03-module-specifications.md](../specs/03-module-specifications.md) §4–6, [specs/01-product-requirements.md](../specs/01-product-requirements.md) F3 F4 F5 F6, [specs/08-acceptance-criteria.md](../specs/08-acceptance-criteria.md) Phase 3

## Global Constraints

- Detector type names: `DetectedQuestion`, `QuestionDetector`
- Silence gap default 800 ms; question-word list from the module spec (do not shorten it)
- Duplicate normalized question within 5 seconds ignored
- LLM timeouts: 30 s first token, 90 s total → `LlmError.code == "LLM_TIMEOUT"`
- System prompt is passed as `system=`, not a message role
- `answer_style` in `{concise, detailed, star_format}`
- Last `max_history_pairs` Q&A in the prompt
- No WebSocket in this phase

---

## File map

- Create: `backend/detection/question_detector.py`
- Create: `backend/context/context_manager.py`
- Create: `backend/llm/claude_client.py`
- Create: `backend/run_answer_console.py`
- Test: `backend/tests/test_question_detector.py`
- Test: `backend/tests/test_context_manager.py`
- Test: `backend/tests/test_claude_client.py`
- Modify: `backend/requirements.txt`

---

### Task 1: QuestionDetector

**Files:**
- Create: `backend/detection/__init__.py`
- Create: `backend/detection/question_detector.py`
- Test: `backend/tests/test_question_detector.py`

**Interfaces:**
- Consumes: `TranscriptEvent`, `QuestionDetectionConfig`
- Produces: `DetectedQuestion | None` from `on_transcript`; `current_buffer_text()`; `reset()`

- [ ] **Step 1: Write the failing tests**

```python
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
```

**Locked extra method (needed for silence without empty STT events):**

```python
def on_silence(self, now_ms: int) -> DetectedQuestion | None: ...
```

Pipeline in later phases must call `on_silence` when no transcript arrives for `silence_gap_ms`. Add this method to the module spec behavior; do not skip it.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_question_detector.py -v`

Expected: FAIL import.

- [ ] **Step 3: Implement detector**

Rules:
- Partials (`is_final=False`) update display buffer only; they never detect
- Finals append/replace the utterance buffer
- Lexical match: ends with `?` OR starts with (casefold) one of: `what`, `why`, `how`, `when`, `where`, `who`, `which`, `can you`, `could you`, `would you`, `tell me`, `describe`, `explain`, `walk me through`, `have you`, `do you`, `did you`, `are you`
- Detect only when `on_silence` gap ≥ `silence_gap_ms` **and** (lexical match OR `classify_fn(buffer)` is True)
- If `use_llm_fallback_classifier` is False, skip classifier; silence + non-lexical → no detect
- If classifier raises, treat as not a question
- Normalize for duplicates: lowercase, strip, collapse whitespace
- `reset()` clears buffer and last-emitted question

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest backend/tests/test_question_detector.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/detection backend/tests/test_question_detector.py
git commit -m "feat: detect completed questions with silence and lexical heuristics"
```

---

### Task 2: ContextManager

**Files:**
- Create: `backend/context/__init__.py`
- Create: `backend/context/context_manager.py`
- Test: `backend/tests/test_context_manager.py`

**Interfaces:**
- Consumes: `ContextConfig`, `answer_style`
- Produces: `build_messages(question) -> list[dict]` with one `{"role":"user","content":...}`; `system_prompt` property

- [ ] **Step 1: Write the failing tests**

```python
from backend.config.schema import ContextConfig
from backend.context.context_manager import ContextManager

CFG = ContextConfig(max_history_pairs=2, resume_path=None, job_description="")


def test_includes_resume_jd_and_question():
    cm = ContextManager(CFG, answer_style="concise")
    cm.set_resume("Built APIs in Python")
    cm.set_job_description("Backend engineer")
    msgs = cm.build_messages("What is your stack?")
    assert msgs[0]["role"] == "user"
    body = msgs[0]["content"]
    assert "Built APIs in Python" in body
    assert "Backend engineer" in body
    assert "What is your stack?" in body
    assert "first person" in cm.system_prompt.lower() or "speaking" in cm.system_prompt.lower()


def test_history_truncated():
    cm = ContextManager(CFG, answer_style="concise")
    cm.add_qa_pair("Q1", "A1")
    cm.add_qa_pair("Q2", "A2")
    cm.add_qa_pair("Q3", "A3")
    body = cm.build_messages("Q4")[0]["content"]
    assert "Q1" not in body
    assert "Q2" in body and "Q3" in body


def test_star_style_mentions_result():
    cm = ContextManager(CFG, answer_style="star_format")
    assert "situation" in cm.system_prompt.lower() or "result" in cm.system_prompt.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_context_manager.py -v`

Expected: FAIL import.

- [ ] **Step 3: Implement ContextManager**

`system_prompt` per style from the module spec. Missing resume/JD inlined as `(none provided)`. History newest-last. `set_answer_style` updates the template.

- [ ] **Step 4: Run tests**

Run: `python -m pytest backend/tests/test_context_manager.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/context backend/tests/test_context_manager.py
git commit -m "feat: assemble interview prompts from resume, JD, and history"
```

---

### Task 3: ClaudeClient with fake transport

**Files:**
- Create: `backend/llm/__init__.py`
- Create: `backend/llm/claude_client.py`
- Test: `backend/tests/test_claude_client.py`
- Modify: `backend/requirements.txt` add `anthropic==0.42.0`

**Interfaces:**
- Consumes: `LlmConfig`, `api_key`
- Produces: `stream_answer` async iterator of `str`; `classify_is_question`; `LlmError`; `cancel_current`

- [ ] **Step 1: Write the failing tests**

```python
import pytest

from backend.config.schema import LlmConfig
from backend.llm.claude_client import ClaudeClient, LlmError

CFG = LlmConfig(model="claude-sonnet-4-6", max_tokens=50, temperature=0.4, answer_style="concise")


@pytest.mark.asyncio
async def test_stream_yields_deltas():
    client = ClaudeClient(CFG, api_key="x", transport="fake")
    tokens = []
    async for t in client.stream_answer("sys", [{"role": "user", "content": "hi"}]):
        tokens.append(t)
    assert tokens == ["In my ", "previous role."]


@pytest.mark.asyncio
async def test_timeout_raises():
    client = ClaudeClient(CFG, api_key="x", transport="fake_timeout")
    with pytest.raises(LlmError) as ei:
        async for _ in client.stream_answer("sys", [{"role": "user", "content": "hi"}], timeout_s=0.01):
            pass
    assert ei.value.code == "LLM_TIMEOUT"


@pytest.mark.asyncio
async def test_classify_true():
    client = ClaudeClient(CFG, api_key="x", transport="fake")
    assert await client.classify_is_question("What is Redis?") is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_claude_client.py -v`

Expected: FAIL import.

- [ ] **Step 3: Implement client**

- `transport="fake"`: yield `"In my "`, `"previous role."`; `classify_is_question` returns True if `?` in text or starts with `what`
- `transport="fake_timeout"`: `asyncio.sleep(1)` then yield (test uses 0.01s timeout)
- `transport="anthropic"` (default when key present): use `anthropic.AsyncAnthropic`. Stream text deltas. First-token timeout `timeout_s` (default 30). Total 90s. API errors → `LlmError("LLM_API_ERROR", str(e))`
- `cancel_current`: cancel the asyncio task / break the stream

- [ ] **Step 4: Run tests**

Run: `python -m pytest backend/tests/test_claude_client.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/llm backend/tests/test_claude_client.py backend/requirements.txt
git commit -m "feat: stream Claude answer tokens with timeout errors"
```

---

### Task 4: Console answer runner

**Files:**
- Create: `backend/run_answer_console.py`

**Interfaces:**
- Consumes: capture, STT, detector, context, Claude
- Produces: printed tokens; CLI `--resume` and `--jd` strings

- [ ] **Step 1: Write runner**

Load config. If no `ANTHROPIC_API_KEY`, print `MISSING_API_KEY` and exit 2.

Wire: loopback → transcriber → on final `detector.on_transcript`; every 50ms `detector.on_silence(now)`. On `DetectedQuestion`, `build_messages`, `stream_answer`, print tokens without newline then `print()` on complete. `add_qa_pair` after complete.

CLI: `--resume TEXT --jd TEXT`.

- [ ] **Step 2: Manual verification**

With a real key in `.env`, play a spoken question. Expected: streamed answer in first person. Without key: exit 2, no hang.

- [ ] **Step 3: Commit**

```bash
git add backend/run_answer_console.py
git commit -m "feat: console pipeline from detected question to streamed answer"
```

---

## Phase 3 acceptance

- [ ] Detector, context, and LLM unit tests pass
- [ ] Spoken question prints streamed tokens then a full answer when API key is set
- [ ] Duplicate questions within 5s do not fire twice

**Stop here. Do not implement WebSocket.**
