from __future__ import annotations

from backend.config.schema import ContextConfig

_NONE = "(none provided)"

_SHARED = (
    "You are the candidate answering interview questions. Answer the current question directly. "
    "Do not describe the interview room, the interviewer, your notes, or your feelings. "
    "Do not tell a story about answering. No markdown headings. "
    "Always format the entire answer as short bullet points (one idea per line, each starting with '- '). "
    "Do not write paragraphs or long sentences."
)

_PROMPTS = {
    "concise": (
        f"{_SHARED} "
        "Use 3 to 6 first person bullet points."
    ),
    "detailed": (
        f"{_SHARED} "
        "Use 6 to 10 first person bullet points. Stay specific and practical."
    ),
    "star_format": (
        f"{_SHARED} "
        "Cover situation, task, action, and result as bullet points "
        "(about 1 to 2 bullets each). Do not label the sections STAR."
    ),
}


class ContextManager:
    def __init__(self, config: ContextConfig, answer_style: str):
        self._config = config
        self._resume = ""
        self._job_description = config.job_description or ""
        self._history: list[tuple[str, str]] = []
        self.set_answer_style(answer_style)

    @property
    def system_prompt(self) -> str:
        return self._system_prompt

    def set_resume(self, text: str) -> None:
        self._resume = text or ""

    def set_job_description(self, text: str) -> None:
        self._job_description = text or ""

    def set_answer_style(self, style: str) -> None:
        self._system_prompt = _PROMPTS.get(style, _PROMPTS["concise"])

    def add_qa_pair(self, question: str, answer: str) -> None:
        self._history.append((question, answer))
        max_pairs = self._config.max_history_pairs
        if max_pairs <= 0:
            self._history = []
            return
        if len(self._history) > max_pairs:
            self._history = self._history[-max_pairs:]

    def build_messages(self, question: str) -> list[dict]:
        resume = self._resume.strip() or _NONE
        jd = self._job_description.strip() or _NONE
        lines = [
            "Resume:",
            resume,
            "",
            "Job description:",
            jd,
            "",
        ]
        if self._history:
            lines.append("Recent Q&A:")
            for q_text, a_text in self._history:
                lines.append(f"Q: {q_text}")
                lines.append(f"A: {a_text}")
            lines.append("")
        lines.append("Current question:")
        lines.append(question)
        lines.append("")
        lines.append("Reply with bullet points only (each line starts with '- ').")
        return [{"role": "user", "content": "\n".join(lines)}]
