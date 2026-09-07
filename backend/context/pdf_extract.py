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
