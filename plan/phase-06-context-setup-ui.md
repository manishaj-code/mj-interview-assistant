# Phase 6: Context and Setup UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Stop after this phase.** Requires Phase 5 complete. Do not start Phase 7.

**Goal:** User uploads a resume (PDF/text) and pastes a job description; both go into every LLM prompt. Missing API key blocks Start.

**Architecture:** `extract_resume_text` in the backend. Setup window in Electron sends `extract_resume` and `update_context`. Overlay Start stays disabled when `missing_api_key` is true.

**Tech Stack:** pypdf, existing Electron windows

**Spec:** [specs/06-ui-requirements.md](../specs/06-ui-requirements.md) §2, [specs/03-module-specifications.md](../specs/03-module-specifications.md) §5, [specs/05-websocket-contract.md](../specs/05-websocket-contract.md) `extract_resume` / `context_updated`, [specs/08-acceptance-criteria.md](../specs/08-acceptance-criteria.md) Phase 6

## Global Constraints

- PDF via `pypdf`; `.txt`/`.md` UTF-8
- Other extensions → `RESUME_PARSE_FAILED`
- Path comes from Electron Open dialog only
- `update_context` requires both `resume_text` and `job_description` (use `""` if empty)
- Do not implement Settings or History screens in this phase
- Do not implement packaging

---

## File map

- Create: `backend/context/pdf_extract.py`
- Modify: `backend/pipeline.py` (`extract_resume`)
- Modify: `backend/requirements.txt` add `pypdf==5.1.0`
- Test: `backend/tests/test_pdf_extract.py`
- Create: `electron/renderer/setup.html`
- Create: `electron/renderer/setup.js`
- Modify: `electron/main.js` (real Setup window + open dialog)

---

### Task 1: extract_resume_text

**Files:**
- Create: `backend/context/pdf_extract.py`
- Test: `backend/tests/test_pdf_extract.py`

**Interfaces:**
- Consumes: `Path`
- Produces: `str` or `ValueError`

- [ ] **Step 1: Write failing tests**

```python
from pathlib import Path

import pytest

from backend.context.pdf_extract import extract_resume_text


def test_txt(tmp_path: Path):
    p = tmp_path / "r.txt"
    p.write_text("Hello resume", encoding="utf-8")
    assert extract_resume_text(p) == "Hello resume"


def test_md(tmp_path: Path):
    p = tmp_path / "r.md"
    p.write_text("# Name\nBio", encoding="utf-8")
    assert "Bio" in extract_resume_text(p)


def test_pdf(tmp_path: Path):
    from pypdf import PdfWriter
    from pypdf.generic import NameObject, create_string_object
    # Write a one-page PDF with text using pypdf
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    pdf_path = tmp_path / "r.pdf"
    writer.write(pdf_path)
    text = extract_resume_text(pdf_path)
    assert isinstance(text, str)  # blank page may be empty string; empty is allowed


def test_bad_ext(tmp_path: Path):
    p = tmp_path / "r.docx"
    p.write_bytes(b"x")
    with pytest.raises(ValueError):
        extract_resume_text(p)
```

Blank PDF may yield `""`. Add a second PDF test that uses a known fixture: write `tests/fixtures/resume_min.pdf` by generating with reportlab **or** skip extra deps and treat empty PDF as success plus a txt test as the content test. **Locked:** do not add reportlab. Content correctness is covered by `.txt`. PDF test only asserts no exception and returns `str`.

- [ ] **Step 2: Run to verify fail**

Run: `python -m pytest backend/tests/test_pdf_extract.py -v`

Expected: FAIL import.

- [ ] **Step 3: Implement**

```python
from pathlib import Path
from pypdf import PdfReader

def extract_resume_text(file_path: Path) -> str:
    suffix = file_path.suffix.lower()
    if suffix in {".txt", ".md"}:
        return file_path.read_text(encoding="utf-8")
    if suffix == ".pdf":
        reader = PdfReader(str(file_path))
        return "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    raise ValueError(f"unsupported resume type: {suffix}")
```

Pipeline `extract_resume(path)`: call this, `context.set_resume`, broadcast `context_updated` with counts and `resume_preview` first 200 chars. On exception: broadcast `error` `RESUME_PARSE_FAILED` `fatal: false`.

- [ ] **Step 4: Tests pass + commit**

Run: `python -m pytest backend/tests/test_pdf_extract.py backend/tests/test_pipeline.py -v`

```bash
git add backend/context/pdf_extract.py backend/tests/test_pdf_extract.py backend/pipeline.py backend/requirements.txt
git commit -m "feat: extract resume text from pdf and plaintext files"
```

---

### Task 2: Setup window

**Files:**
- Create: `electron/renderer/setup.html`
- Create: `electron/renderer/setup.js`
- Modify: `electron/main.js`
- Modify: `electron/preload.js` if needed for `openResumeDialog`

**Interfaces:**
- Consumes: `extract_resume`, `update_context`, `context_updated`, `status.missing_api_key`
- Produces: Setup UI

- [ ] **Step 1: Preload dialog API**

Add:

```javascript
openResumeDialog: () => ipcRenderer.invoke("open-resume-dialog"),
```

Main:

```javascript
ipcMain.handle("open-resume-dialog", async () => {
  const r = await dialog.showOpenDialog({
    properties: ["openFile"],
    filters: [{ name: "Resume", extensions: ["pdf", "txt", "md"] }],
  });
  if (r.canceled || !r.filePaths[0]) return null;
  return r.filePaths[0];
});
```

`open-setup` creates a normal (non-transparent) BrowserWindow loading `setup.html`.

- [ ] **Step 2: Setup HTML/JS**

Fields:
- Banner if `missing_api_key`
- Button “Upload resume” → dialog → `{type:"extract_resume", payload:{path}}`
- Show `resume_preview` and `resume_chars` from `context_updated`
- Textarea JD
- Save JD → `{type:"update_context", payload:{resume_text: "", job_description: textarea}}` (empty `resume_text` keeps the stored resume; see WS contract).

- Continue button focuses overlay (`ipcRenderer.send("show-overlay")`).

- [ ] **Step 3: Overlay Start + missing key**

When `missingApiKey`, Start button disabled and banner: `Add ANTHROPIC_API_KEY to .env and restart backend.`

- [ ] **Step 4: Manual verification**

1. Launch app. Open Setup. Upload `.txt` resume → preview chars > 0.
2. Paste JD, Save. Ask a question → answer uses resume facts.
3. Upload PDF resume → `context_updated` or visible preview.
4. Remove API key, restart backend → Start disabled, Setup banner shown.

- [ ] **Step 5: Commit**

```bash
git add electron specs/05-websocket-contract.md
git commit -m "feat: setup UI for resume upload and job description"
```

---

## Phase 6 acceptance

- [ ] PDF and txt extract tests pass
- [ ] Resume + JD affect the next answer
- [ ] Missing API key blocks Start and shows the Setup banner

**Stop here. Do not implement History, Settings, or packaging.**
