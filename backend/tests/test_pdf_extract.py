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

    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    pdf_path = tmp_path / "r.pdf"
    writer.write(pdf_path)
    text = extract_resume_text(pdf_path)
    assert isinstance(text, str)


def test_bad_ext(tmp_path: Path):
    p = tmp_path / "r.docx"
    p.write_bytes(b"x")
    with pytest.raises(ValueError):
        extract_resume_text(p)
